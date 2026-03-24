#!/usr/bin/env python3
"""
lead_scraper.py
===============
Script para buscar clientes potenciales (leads) de un nicho específico
que NO tengan sitio web, usando la API oficial de Google Places.

Datos recopilados por cada negocio:
  - Nombre del negocio
  - Enlace de Google Maps
  - Número de teléfono (formato internacional / WhatsApp)

Uso básico:
  python lead_scraper.py --count 100 --niche "Dental clinic" --location "Europe"

Con modo IA:
  python lead_scraper.py --count 100 --niche "Dental clinic" --location "Europe" --use-ai

Ver todas las opciones:
  python lead_scraper.py --help
"""

import os
import sys
import time
import json
import csv
import argparse
import logging
from pathlib import Path
from typing import Optional

# Carga las variables de entorno desde el archivo .env (si existe)
# Debe llamarse ANTES de importar cualquier módulo que use os.getenv()
from dotenv import load_dotenv
load_dotenv()

import googlemaps
import phonenumbers
from tqdm import tqdm

# ─────────────────────────────────────────────────────────────────
# Intenta importar OpenAI (solo necesario para el modo --use-ai)
# Si no está instalado o no hay clave, el script funciona igual
# sin IA (se muestra un aviso al usuario).
# ─────────────────────────────────────────────────────────────────
try:
    from openai import OpenAI as _OpenAIClient
    _OPENAI_PACKAGE_AVAILABLE = True
except ImportError:
    _OPENAI_PACKAGE_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────
# Configuración del logger
# ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────

# Campos de Place Details que queremos obtener.
# Cada campo adicional incrementa el costo de la API; solo pedimos
# lo estrictamente necesario para reducir gastos.
PLACE_DETAIL_FIELDS = [
    "name",           # Nombre del negocio
    "formatted_phone_number",   # Teléfono con formato local
    "international_phone_number",  # Teléfono en formato internacional (+xx)
    "website",        # Sitio web (lo usamos para EXCLUIR negocios que sí tienen)
    "url",            # URL de Google Maps del lugar
    "place_id",       # ID único del lugar en Google
    "business_status", # Estado: OPERATIONAL, CLOSED_TEMPORARILY, CLOSED_PERMANENTLY
]

# Tiempo de espera entre peticiones a la API (segundos).
# Google recomienda no superar 10 QPS en Places API.
REQUEST_DELAY = 0.5

# Número máximo de reintentos si la API devuelve un error transitorio
MAX_RETRIES = 3


# ─────────────────────────────────────────────────────────────────
# Clase principal
# ─────────────────────────────────────────────────────────────────

class LeadScraper:
    """
    Busca negocios de un nicho específico que NO tengan sitio web
    usando la Google Places API.

    Parámetros
    ----------
    api_key : str
        Clave de la Google Maps Platform API.
    use_ai : bool
        Si True, usa OpenAI para mejorar las consultas y validar datos.
    openai_api_key : str | None
        Clave de OpenAI (requerida si use_ai=True).
    openai_model : str
        Modelo de OpenAI a usar (por defecto: gpt-4o-mini).
    """

    def __init__(
        self,
        api_key: str,
        use_ai: bool = False,
        openai_api_key: Optional[str] = None,
        openai_model: str = "gpt-4o-mini",
    ):
        # Inicializa el cliente oficial de Google Maps
        self.gmaps = googlemaps.Client(key=api_key)

        # Configura el modo IA
        self.use_ai = use_ai
        self.ai_client: Optional[object] = None

        if use_ai:
            self._init_ai(openai_api_key, openai_model)

    # ── Inicialización IA ──────────────────────────────────────────

    def _init_ai(self, openai_api_key: Optional[str], model: str) -> None:
        """
        Inicializa el cliente de OpenAI.
        Si no está disponible, desactiva el modo IA con un aviso.
        """
        if not _OPENAI_PACKAGE_AVAILABLE:
            logger.warning(
                "El paquete 'openai' no está instalado. "
                "Ejecuta: pip install openai\n"
                "Continuando SIN modo IA."
            )
            self.use_ai = False
            return

        key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        if not key:
            logger.warning(
                "No se encontró OPENAI_API_KEY. "
                "Continuando SIN modo IA."
            )
            self.use_ai = False
            return

        try:
            self.ai_client = _OpenAIClient(api_key=key)
            self.openai_model = model
            # Verificación rápida de que la clave funciona
            self.ai_client.models.list()
            logger.info(f"Modo IA activado (modelo: {model})")
        except Exception as exc:
            logger.warning(
                f"No se pudo conectar con OpenAI ({exc}). "
                "Continuando SIN modo IA."
            )
            self.use_ai = False
            self.ai_client = None

    # ── Generación de consultas de búsqueda ───────────────────────

    def _build_search_queries(self, niche: str, location: str) -> list[str]:
        """
        Genera una lista diversa de consultas para maximizar la cobertura.

        Sin IA: usa variaciones predefinidas del nicho + subregiones europeas.
        Con IA: pide a GPT que genere consultas optimizadas para encontrar
                negocios sin sitio web.

        Retorna
        -------
        list[str]
            Lista de cadenas de búsqueda, de la más específica a la más general.
        """
        if self.use_ai and self.ai_client:
            return self._ai_build_queries(niche, location)

        # ── Modo sin IA ──
        # Variaciones del término del nicho en inglés y español.
        # Se incluyen sinónimos comunes para el nicho dental; para otros
        # nichos se usa solo el término tal como se proporcionó.
        niche_variants = [niche]
        if "dental" in niche.lower() or "dentist" in niche.lower():
            niche_variants += [
                "dentist", "odontólogo", "clínica dental",
                "dental office", "dentista", "orthodontist",
            ]

        # Para Europa, descomponemos en subregiones para mayor cobertura
        # (una sola búsqueda "Europe" no garantiza resultados de todos los países)
        if "europ" in location.lower():
            subregions = [
                "Spain", "France", "Germany", "Italy", "Poland",
                "Romania", "Netherlands", "Belgium", "Portugal",
                "Czech Republic", "Hungary", "Greece", "Sweden",
                "Austria", "Switzerland", "Denmark", "Finland",
                "Norway", "Slovakia", "Croatia", "Bulgaria",
            ]
        else:
            subregions = [location]

        queries: list[str] = []
        for variant in niche_variants:
            for region in subregions:
                queries.append(f"{variant} {region}")

        return queries

    def _ai_build_queries(self, niche: str, location: str) -> list[str]:
        """
        Usa OpenAI para generar consultas de búsqueda optimizadas.
        """
        prompt = (
            f"Genera una lista de 30 consultas de búsqueda para Google Places API "
            f"para encontrar negocios del nicho '{niche}' en '{location}' que "
            f"probablemente NO tengan sitio web (pequeños negocios locales, "
            f"clínicas independientes, etc.).\n"
            f"Devuelve SOLO la lista en formato JSON: [\"consulta1\", \"consulta2\", ...]\n"
            f"Usa variaciones de idioma (inglés, español, francés, alemán, italiano, etc.) "
            f"y diferentes ciudades/regiones de {location}."
        )
        try:
            response = self.ai_client.chat.completions.create(
                model=self.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            raw = response.choices[0].message.content.strip()
            # Extrae el JSON de la respuesta
            start = raw.find("[")
            end = raw.rfind("]") + 1
            queries = json.loads(raw[start:end])
            logger.info(f"IA generó {len(queries)} consultas de búsqueda")
            return queries
        except Exception as exc:
            logger.warning(f"Error al generar consultas con IA ({exc}). Usando modo manual.")
            self.use_ai = False
            return self._build_search_queries(niche, location)

    # ── Búsqueda y extracción de datos ────────────────────────────

    def _text_search_page(
        self, query: str, page_token: Optional[str] = None
    ) -> dict:
        """
        Llama a gmaps.places() (Text Search) con reintentos automáticos.

        La respuesta incluye hasta 20 resultados y puede tener un
        'next_page_token' para obtener más páginas.

        Retorna
        -------
        dict
            Respuesta de la API (campos: status, results, next_page_token)
        """
        for attempt in range(MAX_RETRIES):
            try:
                if page_token:
                    # Google requiere 2 segundos de espera antes de usar un page_token
                    time.sleep(2)
                    return self.gmaps.places(query=query, page_token=page_token)
                return self.gmaps.places(query=query)
            except googlemaps.exceptions.ApiError as exc:
                logger.warning(f"Error API (intento {attempt + 1}/{MAX_RETRIES}): {exc}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)  # Backoff exponencial
                else:
                    raise

    def _get_place_details(self, place_id: str) -> Optional[dict]:
        """
        Obtiene los detalles completos de un lugar por su place_id.

        Solo solicita los campos definidos en PLACE_DETAIL_FIELDS para
        minimizar el costo de la API.

        Retorna
        -------
        dict | None
            Datos del lugar, o None si ocurrió un error.
        """
        for attempt in range(MAX_RETRIES):
            try:
                result = self.gmaps.place(
                    place_id=place_id,
                    fields=PLACE_DETAIL_FIELDS,
                )
                return result.get("result", {})
            except googlemaps.exceptions.ApiError as exc:
                logger.warning(
                    f"Error al obtener detalles de {place_id} "
                    f"(intento {attempt + 1}/{MAX_RETRIES}): {exc}"
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                else:
                    return None

    def _format_phone_for_whatsapp(self, raw_phone: str) -> Optional[str]:
        """
        Convierte un número de teléfono a formato internacional E.164
        apto para WhatsApp (ej: +34 612 345 678 → +34612345678).

        Retorna None si el número no es válido.
        """
        if not raw_phone:
            return None
        try:
            parsed = phonenumbers.parse(raw_phone, None)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
        except phonenumbers.NumberParseException:
            pass
        return None

    def _extract_lead(self, place_id: str) -> Optional[dict]:
        """
        Extrae los datos de un lugar y los valida.

        Regla de negocio:
        - El negocio NO debe tener sitio web.
        - Debe tener nombre, teléfono válido y URL de Google Maps.
        - El estado del negocio debe ser OPERATIONAL.

        Retorna
        -------
        dict | None
            Lead válido, o None si el lugar no cumple los criterios.
        """
        details = self._get_place_details(place_id)
        if not details:
            return None

        # ── Filtro 1: solo negocios operativos ──
        status = details.get("business_status", "OPERATIONAL")
        if status != "OPERATIONAL":
            return None

        # ── Filtro 2: excluir negocios que SÍ tienen sitio web ──
        if details.get("website"):
            return None

        # ── Extracción de datos requeridos ──
        name = details.get("name", "").strip()
        maps_url = details.get("url", "")

        # Prefiere el número internacional; si no, usa el formateado localmente
        raw_phone = details.get("international_phone_number") or \
                    details.get("formatted_phone_number") or ""

        phone = self._format_phone_for_whatsapp(raw_phone)

        # ── Filtro 3: todos los campos obligatorios deben estar presentes ──
        if not name or not maps_url or not phone:
            return None

        return {
            "name": name,
            "phone": phone,        # Formato E.164 para WhatsApp
            "maps_url": maps_url,
            "place_id": place_id,
        }

    def _ai_validate_lead(self, lead: dict, niche: str = "business") -> bool:
        """
        Usa IA para validar que un lead parece auténtico y relevante.
        Solo se llama si --use-ai está activo.

        Parámetros
        ----------
        lead : dict
            Datos del lead a validar.
        niche : str
            Nicho de negocio buscado (se incorpora al prompt para que la IA
            valide correctamente cualquier tipo de negocio, no solo dentales).

        Retorna True si el lead es válido, False si debe descartarse.
        """
        if not self.use_ai or not self.ai_client:
            return True

        prompt = (
            f"Analyze this business and tell me if it looks like a small independent "
            f"'{niche}' business that probably has no significant web presence. "
            f"Reply ONLY with 'YES' or 'NO'.\n"
            f"Name: {lead['name']}\n"
            f"Phone: {lead['phone']}\n"
            f"Maps URL: {lead['maps_url']}"
        )
        try:
            response = self.ai_client.chat.completions.create(
                model=self.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=5,
            )
            answer = response.choices[0].message.content.strip().upper()
            # Accept both English and Spanish affirmative responses
            return answer.startswith("YES") or answer.startswith("SI") or answer.startswith("SÍ")
        except Exception:
            # Si la IA falla, aceptamos el lead (no bloqueamos la búsqueda)
            return True

    # ── Método principal ───────────────────────────────────────────

    def scrape(
        self,
        niche: str,
        location: str,
        count: int,
    ) -> list[dict]:
        """
        Busca exactamente `count` leads del nicho indicado en la ubicación
        indicada, todos sin sitio web y con datos completos.

        Parámetros
        ----------
        niche : str
            Tipo de negocio a buscar (ej: "Dental clinic").
        location : str
            Ubicación (ej: "Europe", "Spain", "Madrid, Spain").
        count : int
            Número exacto de leads a recopilar.

        Retorna
        -------
        list[dict]
            Lista de leads. Cada lead tiene: name, phone, maps_url, place_id.
        """
        leads: list[dict] = []
        seen_place_ids: set[str] = set()  # Evita duplicados

        queries = self._build_search_queries(niche, location)
        logger.info(
            f"Iniciando búsqueda de {count} leads | "
            f"Nicho: {niche} | Ubicación: {location} | "
            f"Modo IA: {'SÍ' if self.use_ai else 'NO'}"
        )

        # Barra de progreso: muestra cuántos leads se han encontrado
        pbar = tqdm(total=count, desc="Leads encontrados", unit="lead")

        for query in queries:
            if len(leads) >= count:
                break

            logger.debug(f"Buscando: {query}")
            page_token = None

            # Itera sobre las páginas de resultados de esta consulta
            while len(leads) < count:
                try:
                    response = self._text_search_page(query, page_token)
                except Exception as exc:
                    logger.error(f"Error en búsqueda '{query}': {exc}")
                    break

                results = response.get("results", [])
                if not results:
                    break

                for place in results:
                    if len(leads) >= count:
                        break

                    place_id = place.get("place_id")
                    if not place_id or place_id in seen_place_ids:
                        continue
                    seen_place_ids.add(place_id)

                    time.sleep(REQUEST_DELAY)

                    lead = self._extract_lead(place_id)
                    if lead is None:
                        continue

                    # Validación adicional con IA (si está activa)
                    if self.use_ai and not self._ai_validate_lead(lead, niche=niche):
                        logger.debug(f"IA descartó: {lead['name']}")
                        continue

                    leads.append(lead)
                    pbar.update(1)
                    logger.debug(
                        f"Lead #{len(leads)}: {lead['name']} | {lead['phone']}"
                    )

                # Pasa a la siguiente página si existe
                page_token = response.get("next_page_token")
                if not page_token:
                    break

        pbar.close()

        if len(leads) < count:
            logger.warning(
                f"Solo se encontraron {len(leads)} leads de los {count} solicitados. "
                f"Considera ampliar la ubicación o el nicho de búsqueda."
            )
        else:
            logger.info(f"Búsqueda completada: {len(leads)} leads encontrados.")

        # Devuelve exactamente `count` leads (o menos si no hubo suficientes)
        return leads[:count]


# ─────────────────────────────────────────────────────────────────
# Exportación de resultados
# ─────────────────────────────────────────────────────────────────

def save_leads(leads: list[dict], output_path: str) -> None:
    """
    Guarda los leads en un archivo CSV o JSON según la extensión del archivo.

    Los campos guardados son:
      - name     : Nombre del negocio
      - phone    : Número de teléfono en formato E.164 (WhatsApp)
      - maps_url : Enlace directo a Google Maps

    Parámetros
    ----------
    leads : list[dict]
        Lista de leads a guardar.
    output_path : str
        Ruta del archivo de salida (.csv o .json).
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.suffix.lower() == ".json":
        with open(path, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)
        logger.info(f"Resultados guardados en JSON: {path}")

    else:
        # Por defecto guarda como CSV (más fácil de abrir en Excel)
        fieldnames = ["name", "phone", "maps_url", "place_id"]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(leads)
        logger.info(f"Resultados guardados en CSV: {path}")


# ─────────────────────────────────────────────────────────────────
# Argumentos de línea de comandos
# ─────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    """
    Define y parsea los argumentos de línea de comandos.

    Ejemplo de uso:
      python lead_scraper.py --count 50 --niche "Dental clinic" --location "Spain"
      python lead_scraper.py --count 100 --use-ai --output leads.json
    """
    parser = argparse.ArgumentParser(
        description=(
            "LeadScraper: busca negocios sin sitio web usando Google Places API.\n"
            "Guarda nombre, teléfono (WhatsApp) y ubicación (Google Maps)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python lead_scraper.py --count 50\n"
            "  python lead_scraper.py --count 100 --niche 'dentist' --location 'Germany'\n"
            "  python lead_scraper.py --count 200 --use-ai --output results.json\n"
        ),
    )

    parser.add_argument(
        "--count", "-n",
        type=int,
        default=50,
        help="Número exacto de leads a buscar (default: 50)",
    )
    parser.add_argument(
        "--niche",
        type=str,
        default="Dental clinic",
        help="Nicho de negocios a buscar (default: 'Dental clinic')",
    )
    parser.add_argument(
        "--location",
        type=str,
        default="Europe",
        help="Ubicación/región de búsqueda (default: 'Europe')",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="leads.csv",
        help="Archivo de salida (.csv o .json) (default: leads.csv)",
    )
    parser.add_argument(
        "--use-ai",
        action="store_true",
        default=False,
        help=(
            "Activa el modo IA (OpenAI) para mejorar búsquedas y validar datos. "
            "Requiere OPENAI_API_KEY en .env. Si la clave falla, continúa sin IA."
        ),
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Muestra información de depuración detallada",
    )

    return parser.parse_args()


# ─────────────────────────────────────────────────────────────────
# Punto de entrada principal
# ─────────────────────────────────────────────────────────────────

def main() -> None:
    """
    Función principal del script.

    Flujo de ejecución:
    1. Lee argumentos de CLI
    2. Valida la clave de API de Google Maps
    3. Inicializa el scraper (con o sin IA)
    4. Ejecuta la búsqueda
    5. Guarda los resultados
    """
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # ── Validar clave de Google Maps ──
    google_api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not google_api_key:
        logger.error(
            "No se encontró GOOGLE_MAPS_API_KEY.\n"
            "1. Copia .env.example a .env\n"
            "2. Rellena tu clave de Google Maps Platform\n"
            "3. Vuelve a ejecutar el script"
        )
        sys.exit(1)

    if args.count <= 0:
        logger.error("--count debe ser un número entero positivo.")
        sys.exit(1)

    # ── Inicializar scraper ──
    scraper = LeadScraper(
        api_key=google_api_key,
        use_ai=args.use_ai,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    )

    # ── Ejecutar búsqueda ──
    leads = scraper.scrape(
        niche=args.niche,
        location=args.location,
        count=args.count,
    )

    if not leads:
        logger.warning("No se encontraron leads. Revisa los parámetros de búsqueda.")
        sys.exit(0)

    # ── Guardar resultados ──
    save_leads(leads, args.output)

    # ── Resumen final ──
    print(f"\n{'═' * 50}")
    print(f"  Leads encontrados : {len(leads)}")
    print(f"  Leads solicitados : {args.count}")
    print(f"  Efectividad       : {len(leads) / args.count * 100:.1f}%")
    print(f"  Archivo de salida : {args.output}")
    print(f"{'═' * 50}\n")


if __name__ == "__main__":
    main()
