# Geodata Converter API

A FastAPI application that converts GeoJSON data into zipped Shapefiles or GeoPackage (GPKG) files. Includes robust validation, support for mixed-geometry flattening, automatic resource cleanup, and a clean API interface.

---

## Features

- **Convert GeoJSON to Shapefile or GPKG:**  
  Accepts a GeoJSON FeatureCollection and outputs either a zipped Shapefile (`.shp`, `.shx`, `.dbf`, `.prj`) or a GeoPackage (`.gpkg`).
- **Mixed Geometry Handling:**  
  Supports mixed `Polygon`/`MultiPolygon` and `LineString`/`MultiLineString` collections by flattening multi-geometries into their single counterparts.
- **Boolean Property Support:**  
  Boolean properties in GeoJSON are automatically converted to integer fields (`0`/`1`) in GPKG output for compatibility.
- **Input Validation:**  
  Validates GeoJSON structure, feature presence, and output file name for security and correctness.
- **CORS Support:**  
  Allows cross-origin requests from configurable origins (e.g., `localhost:5143`).
- **Automatic Resource Cleanup:**  
  Uses FastAPI background tasks to clean up temporary files after response delivery.
- **Comprehensive Testing:**  
  Includes a full test suite using `pytest` and `httpx`.

---

## Requirements

- Python 3.7+
- Key Libraries: `fastapi`, `uvicorn`, `pyshp` (shapefile), `fiona`, `shapely` (implied)
- See `requirements.txt` for full list of dependencies.

---

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/gokturkbrk/geodata-converter-api.git
   cd geodata-converter-api
   ```

2. **Create and activate a virtual environment (recommended):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## Running the API

Start the server with:

```bash
uvicorn main:app --reload
```

The API will be available at [http://127.0.0.1:8000](http://127.0.0.1:8000).

Interactive documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

---

## API Usage

### Endpoint

`POST /convert`

### Request Body

```json
{
  "geojson": { ... },   // A valid GeoJSON FeatureCollection
  "name": "output_name", // Desired base name for output files (no slashes or '..')
  "format": "shp"        // Optional: "shp" (default) or "gpkg"
}
```

### Example Request

```bash
curl -X POST "http://127.0.0.1:8000/convert" \
  -H "Content-Type: application/json" \
  -d '{
    "geojson": {
      "type": "FeatureCollection",
      "features": [
        {
          "type": "Feature",
          "geometry": { "type": "Polygon", "coordinates": [[[0,0],[0,1],[1,1],[0,0]]] },
          "properties": { "id": 1, "active": true }
        },
        {
          "type": "Feature",
          "geometry": { "type": "MultiPolygon", "coordinates": [[[[10,10],[10,11],[11,11],[10,10]]]] },
          "properties": { "id": 2, "active": false }
        }
      ]
    },
    "name": "my_shapes",
    "format": "gpkg"
  }' --output my_shapes.gpkg
```

### Response

- **200 OK:**  
  - For `shp`: Returns a `.zip` file containing the shapefile components.
  - For `gpkg`: Returns a `.gpkg` file.
- **400 Bad Request:**  
  - Invalid GeoJSON, missing features, or invalid name.
- **500 Internal Server Error:**  
  - Unexpected error during conversion.

---

## Behavior & Limitations

- **Geometry Handling:**  
  - Mixed `Polygon`/`MultiPolygon` and `LineString`/`MultiLineString` are flattened to single geometry types.
  - The output file's geometry type is determined by the first feature after flattening. Features with other geometry types are skipped.
- **Properties Schema (IMPORTANT):**  
  - **Schema Inference:** Attribute fields are defined solely based on the properties of the **first feature** in the collection.
  - **Data Loss Risk:** If subsequent features contain properties that are not present in the first feature, those values will be **dropped**. Ensure your first feature contains all potential fields (even with null values) to avoid data loss.
  - Boolean properties are converted to integer fields (`0`/`1`) in GPKG output.
- **Shapefile Field Names:**  
  - Field names are truncated to 10 characters due to the Shapefile format limitation.
- **File Name Validation:**  
  - The `name` parameter must not contain slashes or `..` for security.
- **Resource Cleanup:**  
  - Temporary files are always cleaned up after the response is sent.

---

## Running Tests

1. **Install test dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the test suite:**
   ```bash
   pytest
   ```

---

## Deployment

This application can be easily deployed using Docker.

1. **Build the Docker image:**
   ```bash
   docker build -t geojson2shp-api .
   ```

2. **Run the Docker container:**
   ```bash
   docker run -p 80:80 geojson2shp-api
   ```

The API will be available at `http://localhost`.

---

## Repository

[https://github.com/gokturkbrk/geodata-converter-api](https://github.com/gokturkbrk/geodata-converter-api)

---

## License

MIT License — feel free to use, modify, and distribute.

---

If you have any questions or encounter issues, please open an issue or contact the maintainer.