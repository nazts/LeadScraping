#!/usr/bin/env python3
"""
lead_scraper.py
===============
Script para buscar clientes potenciales (leads) de un nicho específico
usando la API de Apify (actor: compass/crawler-google-places).

Datos recopilados por cada negocio:
  - Nombre del negocio
  - Enlace de Google Maps
  - Número de teléfono (formato internacional / WhatsApp)

Uso básico:
  python lead_scraper.py --count 100 --niche "Dental clinic" --location "Europe"

Solo negocios CON sitio web:
  python lead_scraper.py --count 100 --website-filter include

Indiferente al sitio web:
  python lead_scraper.py --count 100 --website-filter any

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

from apify_client import ApifyClient
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

# Número máximo de lugares que Apify scrapeará por consulta de búsqueda.
# Aumentar este valor devuelve más candidatos pero consume más créditos.
MAX_PLACES_PER_QUERY = 20

# Número de consultas enviadas en cada llamada al actor de Apify.
# Lotes más pequeños reducen el tiempo de espera por ejecución.
APIFY_BATCH_SIZE = 10

# Número máximo de reintentos si la API devuelve un error transitorio
MAX_RETRIES = 3

# Valores válidos para el parámetro website_filter
WEBSITE_FILTER_CHOICES = ("exclude", "include", "any")


# ─────────────────────────────────────────────────────────────────
# Clase principal
# ─────────────────────────────────────────────────────────────────

class LeadScraper:
    """
    Busca negocios de un nicho específico usando la API de Apify
    (actor: compass/crawler-google-places).

    Parámetros
    ----------
    api_token : str
        Token de autenticación de Apify.
    use_ai : bool
        Si True, usa OpenAI para mejorar las consultas y validar datos.
    openai_api_key : str | None
        Clave de OpenAI (requerida si use_ai=True).
    openai_model : str
        Modelo de OpenAI a usar (por defecto: gpt-4o-mini).
    website_filter : str
        Controla el filtro de sitio web:
        - ``"exclude"`` (por defecto): solo negocios SIN sitio web.
        - ``"include"``: solo negocios CON sitio web.
        - ``"any"``: indiferente al sitio web (incluye todos).
    """

    def __init__(
        self,
        api_token: str,
        use_ai: bool = False,
        openai_api_key: Optional[str] = None,
        openai_model: str = "gpt-4o-mini",
        website_filter: str = "exclude",
    ):
        # Inicializa el cliente oficial de Apify
        self._apify = ApifyClient(api_token)

        # Configura el filtro de sitio web
        if website_filter not in WEBSITE_FILTER_CHOICES:
            raise ValueError(
                f"website_filter debe ser 'exclude', 'include' o 'any', "
                f"se recibió: '{website_filter}'"
            )
        self.website_filter = website_filter

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

    def _search_places(self, queries: list[str]) -> list[dict]:
        """
        Ejecuta el actor de Apify 'compass/crawler-google-places' con las
        consultas indicadas y devuelve todos los ítems del dataset resultante.

        Parámetros
        ----------
        queries : list[str]
            Lista de consultas de búsqueda (ej: ["dental clinic Spain"]).

        Retorna
        -------
        list[dict]
            Lista de negocios encontrados por Apify.
        """
        for attempt in range(MAX_RETRIES):
            try:
                run = self._apify.actor("compass/crawler-google-places").call(
                    run_input={
                        "searchStringsArray": queries,
                        "maxCrawledPlacesPerSearch": MAX_PLACES_PER_QUERY,
                        "language": "en",
                        "includeHistogram": False,
                        "includeOpeningHours": False,
                        "includePeopleAlsoBrowse": False,
                    }
                )
                return list(
                    self._apify.dataset(run["defaultDatasetId"]).iterate_items()
                )
            except Exception as exc:
                logger.warning(
                    f"Error en búsqueda Apify (intento {attempt + 1}/{MAX_RETRIES}): {exc}"
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise

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

    def _extract_lead(self, item: dict) -> Optional[dict]:
        """
        Extrae los datos de un ítem devuelto por Apify y los valida.

        Regla de negocio:
        - El filtro de sitio web se aplica según ``self.website_filter``:
            - ``"exclude"``: descarta negocios que tengan sitio web.
            - ``"include"``: descarta negocios que NO tengan sitio web.
            - ``"any"``: acepta independientemente del sitio web.
        - Debe tener nombre, teléfono válido y URL de Google Maps.
        - El negocio no debe estar cerrado permanente ni temporalmente.

        Retorna
        -------
        dict | None
            Lead válido, o None si el lugar no cumple los criterios.
        """
        # ── Filtro 1: solo negocios operativos ──
        if item.get("permanentlyClosed") or item.get("temporarilyClosed"):
            return None

        # ── Filtro 2: filtro de sitio web configurable ──
        if self.website_filter == "exclude" and item.get("website"):
            return None
        if self.website_filter == "include" and not item.get("website"):
            return None
        # "any": no se aplica ningún filtro de sitio web

        # ── Extracción de datos requeridos ──
        name = (item.get("title") or "").strip()
        maps_url = item.get("url") or ""
        raw_phone = item.get("phone") or ""
        place_id = item.get("placeId") or ""

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
        indicada, aplicando el filtro de sitio web configurado y con datos
        completos.

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
        seen_ids: set[str] = set()  # Evita duplicados

        queries = self._build_search_queries(niche, location)
        logger.info(
            f"Iniciando búsqueda de {count} leads | "
            f"Nicho: {niche} | Ubicación: {location} | "
            f"Filtro web: {self.website_filter} | "
            f"Modo IA: {'SÍ' if self.use_ai else 'NO'}"
        )

        # Barra de progreso: muestra cuántos leads se han encontrado
        pbar = tqdm(total=count, desc="Leads encontrados", unit="lead")

        # Envía las consultas en lotes para no sobrecargar una sola ejecución Apify
        for batch_start in range(0, len(queries), APIFY_BATCH_SIZE):
            if len(leads) >= count:
                break

            batch = queries[batch_start: batch_start + APIFY_BATCH_SIZE]
            logger.debug(
                f"Ejecutando búsqueda Apify con {len(batch)} consultas "
                f"(lote {batch_start // APIFY_BATCH_SIZE + 1})..."
            )

            try:
                items = self._search_places(batch)
            except Exception as exc:
                logger.error(f"Error en lote de búsqueda Apify: {exc}")
                continue

            for item in items:
                if len(leads) >= count:
                    break

                # Usa placeId o URL como clave única para evitar duplicados
                uid = item.get("placeId") or item.get("url") or ""
                if not uid or uid in seen_ids:
                    continue
                seen_ids.add(uid)

                lead = self._extract_lead(item)
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
            "LeadScraper: busca negocios usando la API de Apify.\n"
            "Guarda nombre, teléfono (WhatsApp) y ubicación (Google Maps)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python lead_scraper.py --count 50\n"
            "  python lead_scraper.py --count 100 --niche 'dentist' --location 'Germany'\n"
            "  python lead_scraper.py --count 50 --website-filter include\n"
            "  python lead_scraper.py --count 50 --website-filter any\n"
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
        "--website-filter",
        type=str,
        default="exclude",
        choices=list(WEBSITE_FILTER_CHOICES),
        help=(
            "Filtro de sitio web: "
            "'exclude' = solo negocios SIN web (default), "
            "'include' = solo negocios CON web, "
            "'any' = indiferente al web."
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
    2. Valida el token de API de Apify
    3. Inicializa el scraper (con o sin IA)
    4. Ejecuta la búsqueda
    5. Guarda los resultados
    """
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # ── Validar token de Apify ──
    apify_api_token = os.getenv("APIFY_API_TOKEN", "")
    if not apify_api_token:
        logger.error(
            "No se encontró APIFY_API_TOKEN.\n"
            "1. Copia .env.example a .env\n"
            "2. Rellena tu token de Apify (https://console.apify.com/account/integrations)\n"
            "3. Vuelve a ejecutar el script"
        )
        sys.exit(1)

    if args.count <= 0:
        logger.error("--count debe ser un número entero positivo.")
        sys.exit(1)

    # ── Inicializar scraper ──
    scraper = LeadScraper(
        api_token=apify_api_token,
        use_ai=args.use_ai,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        website_filter=args.website_filter,
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
