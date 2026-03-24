# LeadScraping

Recolección de leads que **no tienen sitio web** usando OpenStreetMap
(Nominatim + Overpass). El proyecto reemplaza la integración previa con
Google Maps/Places por fuentes abiertas, eliminando la necesidad de claves
API comerciales.

## Requisitos

- Python 3.10+ y `pip`.
- Dependencias: `pip install -r requirements.txt`.
- No se necesitan claves API para Nominatim/Overpass; sí es obligatorio
  definir un User-Agent propio (se usa uno por defecto).
- Los teléfonos encontrados se normalizan automáticamente a formato E.164,
  listo para WhatsApp.
- (Opcional) `OPENAI_API_KEY` para mejorar búsquedas y validación de datos.

### Variables de entorno relevantes

Puedes sobreescribir los endpoints o ajustes desde `.env`:

```
# Endpoints / configuración OSM
NOMINATIM_URL=https://nominatim.openstreetmap.org/search
OVERPASS_URL=https://overpass-api.de/api/interpreter
OSM_SEARCH_RADIUS=50000          # radio en metros
OSM_USER_AGENT=LeadScraping/1.0 (https://github.com/nazts/LeadScraping)

# Modo IA (opcional)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

## Uso básico

```
python lead_scraper.py --count 100 --niche "Dental clinic" --location "Europe"
```

Con IA (OpenAI):

```
python lead_scraper.py --count 100 --niche "Dental clinic" --location "Europe" --use-ai
```

Más opciones:

```
python lead_scraper.py --help
```

## Flujo de trabajo

1. Geocodifica la ubicación con **Nominatim** (OpenStreetMap).
2. Busca POIs en **Overpass** filtrando negocios sin campo `website`.
3. Normaliza teléfonos a formato E.164 (WhatsApp).
4. Guarda los resultados en CSV o JSON.
