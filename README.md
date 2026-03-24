# 🦷 LeadScraping

Script de Python que busca negocios de un nicho específico (por defecto: **clínicas dentales**) en una región (por defecto: **Europa**) que **no tengan sitio web**, usando la [Google Places API](https://developers.google.com/maps/documentation/places/web-service/overview).

Por cada negocio recopila:
- ✅ **Nombre** del negocio
- ✅ **Número de teléfono** en formato internacional (apto para WhatsApp)
- ✅ **Enlace de Google Maps** directo al local

Solo se guarda un negocio cuando los **tres datos están completos**. La búsqueda garantiza exactamente el número de leads solicitado.

---

## 📋 Tabla de Contenidos

1. [Requisitos](#-requisitos)
2. [Instalación](#-instalación)
3. [Configuración de API Keys](#-configuración-de-api-keys)
4. [Uso básico](#-uso-básico)
5. [Opciones avanzadas](#️-opciones-avanzadas)
6. [Modo IA (opcional)](#-modo-ia-opcional)
7. [Archivos de salida](#-archivos-de-salida)
8. [Cómo funciona el código](#-cómo-funciona-el-código)
9. [Costos de la API](#-costos-de-la-api)
10. [Solución de problemas](#-solución-de-problemas)

---

## 🔧 Requisitos

- Python **3.10** o superior
- Cuenta en [Google Cloud Platform](https://console.cloud.google.com/) con la **Places API** activada
- *(Opcional)* Cuenta en [OpenAI](https://platform.openai.com/) para el modo IA

---

## 📦 Instalación

### 1. Clona el repositorio

```bash
git clone https://github.com/nazts/LeadScraping.git
cd LeadScraping
```

### 2. Crea un entorno virtual (recomendado)

```bash
# Crea el entorno virtual
python -m venv venv

# Actívalo
# En Linux / macOS:
source venv/bin/activate

# En Windows:
venv\Scripts\activate
```

### 3. Instala las dependencias

```bash
pip install -r requirements.txt
```

#### Descripción de las dependencias

| Librería | Versión | Uso |
|---|---|---|
| `googlemaps` | ≥ 4.10.0 | Cliente oficial de Google Maps Platform (Places API) |
| `python-dotenv` | ≥ 1.0.0 | Carga variables de entorno desde el archivo `.env` |
| `phonenumbers` | ≥ 8.13.0 | Valida y formatea números de teléfono internacionales (WhatsApp) |
| `requests` | ≥ 2.31.0 | Peticiones HTTP (dependencia de googlemaps) |
| `tqdm` | ≥ 4.66.0 | Barra de progreso en la terminal |
| `openai` | ≥ 1.30.0 | *(Opcional)* Cliente de OpenAI para el modo IA |

---

## 🔑 Configuración de API Keys

### Google Maps Platform (obligatorio)

1. Ve a [console.cloud.google.com](https://console.cloud.google.com/)
2. Crea un nuevo proyecto (o usa uno existente)
3. Ve a **APIs y servicios → Biblioteca**
4. Busca y activa la **Places API**
5. Ve a **APIs y servicios → Credenciales**
6. Haz clic en **Crear credenciales → Clave de API**
7. Copia la clave generada

> 💡 **Precio**: Google ofrece **$200 USD de crédito gratuito al mes**, lo que cubre miles de búsquedas. La Places Text Search cuesta ~$0.032 por consulta y Place Details ~$0.017 por consulta. Para precios actualizados consulta la [página oficial de precios](https://mapsplatform.google.com/pricing/).

### Configurar el archivo `.env`

```bash
# Copia el archivo de ejemplo
cp .env.example .env

# Edita el archivo .env con tu editor favorito
nano .env   # o: code .env / vim .env
```

Rellena tu archivo `.env`:

```dotenv
GOOGLE_MAPS_API_KEY=AIzaSy...tu_clave_real_aqui...

# Solo si usas --use-ai:
OPENAI_API_KEY=sk-...tu_clave_openai_aqui...
OPENAI_MODEL=gpt-4o-mini
```

> ⚠️ **IMPORTANTE**: Nunca subas el archivo `.env` a GitHub. El `.gitignore` ya lo excluye automáticamente.

---

## 🚀 Uso básico

```bash
# Buscar 50 clínicas dentales en Europa (configuración por defecto)
python lead_scraper.py

# Buscar exactamente 100 leads
python lead_scraper.py --count 100

# Cambiar nicho y ubicación
python lead_scraper.py --count 50 --niche "veterinary clinic" --location "Germany"

# Guardar en JSON en lugar de CSV
python lead_scraper.py --count 100 --output results.json

# Ver todas las opciones disponibles
python lead_scraper.py --help
```

---

## ⚙️ Opciones avanzadas

| Opción | Alias | Por defecto | Descripción |
|---|---|---|---|
| `--count` | `-n` | `50` | Número exacto de leads a buscar |
| `--niche` | — | `"Dental clinic"` | Tipo de negocio a buscar |
| `--location` | — | `"Europe"` | País, ciudad o región |
| `--output` | `-o` | `leads.csv` | Archivo de salida (`.csv` o `.json`) |
| `--use-ai` | — | desactivado | Activa el modo IA con OpenAI |
| `--verbose` | `-v` | desactivado | Muestra logs de depuración |

### Ejemplos adicionales

```bash
# 200 leads en España con salida JSON y modo verbose
python lead_scraper.py --count 200 --location "Spain" --output spain_leads.json -v

# Dentistas en Francia con modo IA
python lead_scraper.py --count 75 --niche "dentiste" --location "France" --use-ai

# Buscar en una ciudad específica
python lead_scraper.py --count 30 --niche "dental" --location "Warsaw, Poland"
```

---

## 🤖 Modo IA (opcional)

El script tiene **dos modos de operación**:

### Sin IA (por defecto)
- Genera consultas de búsqueda usando variaciones predefinidas del nicho
- Para Europa, divide la búsqueda en 20+ países automáticamente
- Más rápido y no requiere créditos de OpenAI

### Con IA (`--use-ai`)
- Usa **OpenAI GPT** para generar 30 consultas de búsqueda optimizadas y diversas
- Valida cada lead con IA para descartar resultados de baja calidad
- Mejora la cobertura geográfica y la diversidad de resultados
- Requiere `OPENAI_API_KEY` en el archivo `.env`

#### Fallback automático
Si el modo IA está activado pero la clave de OpenAI no es válida o se queda sin créditos, el script **continúa automáticamente en modo sin IA** y muestra un aviso en la terminal. De esta manera, la búsqueda nunca se interrumpe.

---

## 📄 Archivos de salida

### CSV (por defecto)
```csv
name,phone,maps_url,place_id
"Clínica Dental López",+34612345678,"https://maps.google.com/?cid=...",ChIJ...
"Cabinet Dentaire Dupont",+33612345678,"https://maps.google.com/?cid=...",ChIJ...
```

### JSON
```json
[
  {
    "name": "Clínica Dental López",
    "phone": "+34612345678",
    "maps_url": "https://maps.google.com/?cid=...",
    "place_id": "ChIJ..."
  }
]
```

Los campos guardados son:
- **`name`**: Nombre del negocio tal como aparece en Google Maps
- **`phone`**: Número en formato E.164 (ej: `+34612345678`), directamente usable en WhatsApp
- **`maps_url`**: Enlace directo al negocio en Google Maps
- **`place_id`**: ID único de Google (útil para referencia o consultas futuras)

---

## 🔍 Cómo funciona el código

### Arquitectura general

```
lead_scraper.py
│
├── LeadScraper (clase principal)
│   ├── _build_search_queries()   → genera lista de búsquedas
│   ├── _text_search_page()       → llama a Places Text Search API
│   ├── _get_place_details()      → llama a Place Details API
│   ├── _extract_lead()           → valida y extrae datos del lead
│   ├── _format_phone_for_whatsapp() → normaliza número de teléfono
│   ├── _ai_validate_lead()       → validación opcional con IA
│   └── scrape()                  → método principal de búsqueda
│
├── save_leads()                  → exporta resultados a CSV o JSON
├── parse_args()                  → argumentos de línea de comandos
└── main()                        → punto de entrada
```

### Flujo de búsqueda paso a paso

1. **Generación de consultas**: El script genera múltiples variaciones de búsqueda (ej: "dentist Spain", "clínica dental France", "Zahnarzt Germany"…) para maximizar la cobertura.

2. **Text Search API**: Para cada consulta, llama a `gmaps.places()` que devuelve hasta 20 resultados por página. Si hay más resultados, usa el `next_page_token` para obtener más páginas.

3. **Filtro sin sitio web**: Llama a `gmaps.place()` (Place Details) para cada resultado y revisa si tiene el campo `website`. Si lo tiene, el negocio se descarta.

4. **Validación de datos**: Solo se acepta un lead si tiene los tres campos obligatorios: **nombre**, **teléfono válido** y **URL de Google Maps**.

5. **Formato WhatsApp**: El número de teléfono se convierte al formato E.164 internacional usando la librería `phonenumbers`.

6. **Control de duplicados**: Se mantiene un conjunto de `place_id` ya procesados para evitar guardar el mismo negocio dos veces.

7. **Exactitud del conteo**: La búsqueda se detiene en cuanto se alcanzan exactamente `count` leads válidos.

### Cosas a tener en cuenta

- **Paginación**: La API devuelve máximo 60 resultados por consulta (3 páginas de 20). Para obtener más de 60 leads por zona, el script usa múltiples consultas con variaciones del nicho y diferentes subregiones.
- **Rate limiting**: El script espera 0.5 segundos entre cada llamada a Place Details y 2 segundos antes de usar un `page_token` (requisito de Google).
- **Negocios sin teléfono**: Muchos negocios en Google Maps no tienen teléfono registrado; estos se descartan automáticamente. Esto es especialmente común en zonas rurales.
- **Cobertura europea**: Por defecto, la búsqueda cubre 20+ países europeos. Si se necesita mayor cobertura de un país específico, usa `--location "Germany"` directamente.

---

## 💰 Costos de la API

Google Maps Platform ofrece **$200 USD de crédito gratuito mensual**. Los precios aproximados son los siguientes (verifica los precios actuales en la [página oficial](https://mapsplatform.google.com/pricing/)):

| Operación | Costo por llamada | Leads procesados con $200 |
|---|---|---|
| Places Text Search | $0.032 | ~6,250 búsquedas |
| Place Details (Basic) | $0.017 | ~11,764 detalles |

Para obtener 100 leads válidos, el script puede procesar 300-500 candidatos (porque muchos tienen website o les faltan datos). Esto cuesta aproximadamente **$5-$10 USD**, bien dentro del crédito gratuito.

---

## 🐛 Solución de problemas

### "No se encontró GOOGLE_MAPS_API_KEY"
```bash
# Verifica que el archivo .env existe y tiene la clave
cat .env
```

### "REQUEST_DENIED" o "This API project is not authorized"
- Verifica que la **Places API** está activada en tu proyecto de Google Cloud
- Revisa que la clave no tenga restricciones de IP que bloqueen tu máquina

### Pocos resultados encontrados
- Amplía la búsqueda: `--location "Western Europe"` o añade más países
- Cambia el nicho: `--niche "dentist"` en lugar de `"Dental clinic"`
- Usa el modo `--use-ai` para consultas más diversas

### Error de OpenAI en modo `--use-ai`
El script continúa automáticamente sin IA. Verifica tu clave en [platform.openai.com](https://platform.openai.com/api-keys) y los créditos disponibles en tu cuenta.
