# LeadScraping

Este proyecto permite la extracción de información de leads utilizando diversas técnicas de scraping y una integración con OpenStreetMap para la geocodificación.

## Requisitos

- No se requieren claves API para Nominatim.
- Las claves de OpenAI son opcionales para ciertas funcionalidades.

## Cómo funciona

La función `_geocode_location` utiliza Nominatim para obtener las coordenadas de ubicación a partir de direcciones. La implementación actual busca en una base de datos de leads y extrae información relevante utilizando la técnica de scraping definida en `lead_scraper.py`. 

### Ejemplo de uso

```python
# Insertar aquí ejemplos de uso
```

Este enfoque permite obtener resultados precisos y actualizados, ajustándose a las necesidades de scraping del proyecto.