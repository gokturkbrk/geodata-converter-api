# GeoJSON to Shapefile/GeoPackage Converter API

This project provides a FastAPI-based API to convert GeoJSON data into either Shapefile or GeoPackage formats.

## Capabilities

- **Convert GeoJSON**: Accepts `FeatureCollection` and converts to:
    - **Shapefile**: Returns a `.zip` containing `.shp`, `.shx`, `.dbf`, `.prj`.
    - **GeoPackage**: Returns a `.gpkg` file.
- **Geometry Flattening**: Automatically converts `MultiPolygon` -> `Polygon` and `MultiLineString` -> `LineString` to handle mixed collections.
- **Validation**: Validates GeoJSON structure and output filenames.

## API Interface

### `POST /convert`

**Input (JSON):**
```json
{
  "geojson": { "type": "FeatureCollection", "features": [...] },
  "name": "output_filename_base",
  "format": "shp" // or "gpkg"
}
```

**Output:**
- Binary file stream (`application/zip` or `application/geopackage+sqlite3`).

## Setup & Run

1.  **Install**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Run**:
    ```bash
    uvicorn main:app --reload
    ```
    Server starts at `http://127.0.0.1:8000`.

## Testing

Run tests with `pytest`.