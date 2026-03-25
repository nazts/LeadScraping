# 🦷 LeadScraping

Script de Python que busca negocios de un nicho específico (por defecto: **clínicas dentales**) en una región (por defecto: **Europa**) que **no tengan sitio web**, usando la [API de Apify](https://apify.com/) (actor [`compass/crawler-google-places`](https://apify.com/compass/crawler-google-places)).

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
- Cuenta en [Apify](https://apify.com/) con un **API Token** válido
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
| `apify-client` | ≥ 2.5.0 | Cliente oficial de Apify (ejecuta el actor Google Maps scraper) |
| `python-dotenv` | ≥ 1.0.0 | Carga variables de entorno desde el archivo `.env` |
| `phonenumbers` | ≥ 8.13.0 | Valida y formatea números de teléfono internacionales (WhatsApp) |
| `requests` | ≥ 2.31.0 | Peticiones HTTP |
| `tqdm` | ≥ 4.66.0 | Barra de progreso en la terminal |
| `openai` | ≥ 1.30.0 | *(Opcional)* Cliente de OpenAI para el modo IA |

---

## 🔑 Configuración de API Keys

### Apify (obligatorio)

1. Ve a [apify.com](https://apify.com/) y crea una cuenta (hay plan gratuito)
2. Accede a **Console → Settings → Integrations**
3. En la sección **API tokens**, haz clic en **+ Add new token**
4. Asigna un nombre (ej: "LeadScraping") y copia el token generado

> 💡 **Precio**: Apify ofrece un **plan gratuito** con créditos mensuales suficientes para miles de búsquedas. Cada ejecución del actor consume unidades de cómputo (CU). Para precios actualizados consulta la [página oficial de precios](https://apify.com/pricing).

### Configurar el archivo `.env`

```bash
# Copia el archivo de ejemplo
cp .env.example .env

# Edita el archivo .env con tu editor favorito
nano .env   # o: code .env / vim .env
```

Rellena tu archivo `.env`:

```dotenv
APIFY_API_TOKEN=apify_api_...tu_token_real_aqui...

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
"Clínica Dental López",+34612345678,"https://www.google.com/maps/place/...",ChIJ...
"Cabinet Dentaire Dupont",+33612345678,"https://www.google.com/maps/place/...",ChIJ...
```

### JSON
```json
[
  {
    "name": "Clínica Dental López",
    "phone": "+34612345678",
    "maps_url": "https://www.google.com/maps/place/...",
    "place_id": "ChIJ..."
  }
]
```

Los campos guardados son:
- **`name`**: Nombre del negocio tal como aparece en Google Maps
- **`phone`**: Número en formato E.164 (ej: `+34612345678`), directamente usable en WhatsApp
- **`maps_url`**: Enlace directo al negocio en Google Maps
- **`place_id`**: ID único de Google Maps (útil para referencia o consultas futuras)

---

## 🔍 Cómo funciona el código

### Arquitectura general

```
lead_scraper.py
│
├── LeadScraper (clase principal)
│   ├── _build_search_queries()   → genera lista de búsquedas
│   ├── _search_places()          → llama al actor de Apify (Google Maps scraper)
│   ├── _extract_lead()           → valida y extrae datos del ítem Apify
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

2. **Apify Actor**: Las consultas se envían en lotes al actor `compass/crawler-google-places` en Apify. El actor scrapeea Google Maps y devuelve resultados enriquecidos (nombre, teléfono, web, URL de Maps, etc.) sin necesidad de llamadas adicionales.

3. **Filtro sin sitio web**: Cada ítem del dataset de Apify se examina para descartar negocios que tengan el campo `website` relleno.

4. **Validación de datos**: Solo se acepta un lead si tiene los tres campos obligatorios: **nombre**, **teléfono válido** y **URL de Google Maps**.

5. **Formato WhatsApp**: El número de teléfono se convierte al formato E.164 internacional usando la librería `phonenumbers`.

6. **Control de duplicados**: Se mantiene un conjunto de IDs ya procesados para evitar guardar el mismo negocio dos veces.

7. **Exactitud del conteo**: La búsqueda se detiene en cuanto se alcanzan exactamente `count` leads válidos.

### Cosas a tener en cuenta

- **Lotes de consultas**: Las consultas se envían en lotes de 10 al actor de Apify. Cada ejecución devuelve hasta 20 resultados por consulta (configurable con `MAX_PLACES_PER_QUERY`).
- **Negocios sin teléfono**: Muchos negocios en Google Maps no tienen teléfono registrado; estos se descartan automáticamente. Esto es especialmente común en zonas rurales.
- **Cobertura europea**: Por defecto, la búsqueda cubre 20+ países europeos. Si se necesita mayor cobertura de un país específico, usa `--location "Germany"` directamente.

---

## 💰 Costos de la API

Apify ofrece un **plan gratuito** con créditos mensuales de cómputo (CU). Los precios aproximados son (verifica los precios actuales en la [página oficial](https://apify.com/pricing)):

| Plan | Créditos (CU/mes) | Uso orientativo |
|---|---|---|
| Free | 5 CU | ~500–1.000 lugares scrapeados |
| Starter ($49/mes) | 75 CU | ~7.500–15.000 lugares |
| Scale ($499/mes) | 1.000 CU | ~100.000+ lugares |

Cada ejecución del actor `compass/crawler-google-places` consume aproximadamente **0.005–0.01 CU por lugar** scrapeado. Para obtener 100 leads válidos, el script puede procesar 300–500 candidatos, lo que supone aproximadamente **1.5–5 CU**, bien dentro del plan gratuito.

---

## 🐛 Solución de problemas

### "No se encontró APIFY_API_TOKEN"
```bash
# Verifica que el archivo .env existe y tiene el token
cat .env
```

### "Unauthorized" o "Authentication failed"
- Verifica que el token es correcto en [console.apify.com/account/integrations](https://console.apify.com/account/integrations)
- Asegúrate de que el token tiene permisos de ejecución de actores

### Pocos resultados encontrados
- Amplía la búsqueda: `--location "Western Europe"` o añade más países
- Cambia el nicho: `--niche "dentist"` en lugar de `"Dental clinic"`
- Usa el modo `--use-ai` para consultas más diversas

### Error de OpenAI en modo `--use-ai`
El script continúa automáticamente sin IA. Verifica tu clave en [platform.openai.com](https://platform.openai.com/api-keys) y los créditos disponibles en tu cuenta.
