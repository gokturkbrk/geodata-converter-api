# GeoJSON to Shapefile & GeoPackage Conversion API

This is a FastAPI application that converts GeoJSON data to either a Shapefile (zipped) or a GeoPackage file.

## Features

- Converts GeoJSON to Shapefile (`.shp`, `.shx`, `.dbf`, `.prj`) or GeoPackage (`.gpkg`).
- Packages Shapefile components into a single `.zip` file. GeoPackage is returned as a single `.gpkg` file.
- Validates input GeoJSON and parameters.
- Handles different geometry types (Point, LineString, Polygon and their Multi* versions). For Shapefile output, all features in a single request must be of the same primary geometry type. For GeoPackage, this is also generally true as Fiona schema is derived from the first feature.
- Handles mixed collections of `Polygon`/`MultiPolygon` and `LineString`/`MultiLineString` by flattening them into a single geometry type for processing.
- Skips unsupported or mismatched geometry types within a single request.

## Setup and Running the Application

### 1. Prerequisites

- Python 3.7+

### 2. Installation

1.  **Clone the repository (or download the files):**
    ```bash
    git clone <repository_url>
    cd geojson2shp-api
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

### 3. Running the API

To run the API server, use `uvicorn`:

```bash
uvicorn main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

### 4. Running Tests

The project uses `pytest` for testing. To run the tests, first ensure you have installed the development dependencies:

```bash
pip install -r requirements.txt
```

Then, run `pytest` from the root directory:

```bash
pytest
```

## API Usage

You can access the interactive API documentation (Swagger UI) at `http://127.0.0.1:8000/docs`.

### Endpoint: `/convert`

- **Method:** `POST`
- **Description:** Converts a GeoJSON object to a zipped Shapefile or a GeoPackage file.
- **Request Body:**

  ```json
  {
    "geojson": {
      "type": "FeatureCollection",
      "features": [
        {
          "type": "Feature",
          "geometry": {
            "type": "Point",
            "coordinates": [102.0, 0.5]
          },
          "properties": {
            "prop0": "value0"
          }
        }
      ]
    },
    "name": "my_data",
    "format": "shp"
  }
  ```

- **Parameters:**
  - `geojson` (object, required): A valid GeoJSON `FeatureCollection`.
  - `name` (string, required): The desired base name for the output file(s).
  - `format` (string, optional): The desired output format. Can be `"shp"` (default) or `"gpkg"`.

- **Success Response:**
  - **Code:** `200 OK`
  - **Content:**
    - If `format` is `"shp"`: A zip file (`application/zip`) named `{name}.zip` containing the shapefile components.
    - If `format` is `"gpkg"`: A GeoPackage file (`application/geopackage+sqlite3`) named `{name}.gpkg`.

- **Error Responses:**
  - **Code:** `400 Bad Request`
    - If the `geojson` is invalid or missing.
    - If the `name` is invalid.
    - If the GeoJSON contains no features or unsupported geometry types for the selected format.
  - **Code:** `422 Unprocessable Entity`
    - If the `format` parameter is invalid.
  - **Code:** `500 Internal Server Error`
    - If an unexpected error occurs during the conversion process.

### Example `curl` commands:

**For Shapefile (default):**

```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/convert' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "geojson": {
    "type": "FeatureCollection",
    "name": "test-points",
    "features": [
      {
        "type": "Feature",
        "properties": { "id": 1 },
        "geometry": {
          "type": "Point",
          "coordinates": [ -122.4194, 37.7749 ]
        }
      },
      {
        "type": "Feature",
        "properties": { "id": 2 },
        "geometry": {
          "type": "Point",
          "coordinates": [ -74.0060, 40.7128 ]
        }
      }
    ]
  },
  "name": "points_shapefile"
}' \
--output points_shapefile.zip
```

## Limitations & Behavior

--output points_shapefile.zip
```

**For GeoPackage:**

```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/convert' \
  -H 'accept: application/json' \ # Or application/geopackage+sqlite3
  -H 'Content-Type: application/json' \
  -d '{
  "geojson": {
    "type": "FeatureCollection",
    "name": "test-points-gpkg",
    "features": [
      {
        "type": "Feature",
        "properties": { "id": 1, "name": "Point A" },
        "geometry": {
          "type": "Point",
          "coordinates": [ -100, 40 ]
        }
      }
    ]
  },
  "name": "points_data",
  "format": "gpkg"
}' \
--output points_data.gpkg
```

## Limitations & Behavior

- **Geometry Handling:**
  - The service can process a mix of `Polygon` and `MultiPolygon` features, or a mix of `LineString` and `MultiLineString` features in a single request. `Multi*` geometries are automatically flattened into their singular counterparts (e.g., `MultiPolygon` becomes multiple `Polygon` features).
  - The output file's geometry type (and schema for GeoPackage) is determined by the first feature in the processed list. Any feature whose geometry type does not match the first feature's type will be skipped. For example, if the first feature is a `Polygon`, all `Point` and `LineString` features in the request will generally be ignored or cause issues.

- **Properties Schema:** The attribute fields for the output file are created based on the properties of the *first* feature in the GeoJSON. All subsequent features are expected to have a compatible properties structure.

- **Shapefile Field Names:** The Shapefile format limits field names to 10 characters. Property keys from your GeoJSON that are longer than this will be truncated when exporting to Shapefile. This limitation does not apply to GeoPackage.