import pytest
from fastapi.testclient import TestClient
import zipfile
import io
import json

from main import app

client = TestClient(app)

# Fixtures for test data
@pytest.fixture
def points_geojson():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [10, 20]},
                "properties": {"name": "A"},
            }
        ],
    }

@pytest.fixture
def polygons_geojson():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
                },
                "properties": {"id": 1},
            }
        ],
    }

@pytest.fixture
def mixed_polygons_geojson():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]],
                },
                "properties": {"type": "single"},
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [[[10, 10], [10, 11], [11, 11], [10, 10]]],
                        [[[20, 20], [20, 21], [21, 21], [20, 20]]],
                    ],
                },
                "properties": {"type": "multi"},
            },
        ],
    }

@pytest.fixture
def mixed_incompatible_geojson():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [0, 0]},
                "properties": {"id": 1},
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[10, 10], [10, 11], [11, 11], [10, 10]]],
                },
                "properties": {"id": 2},
            },
        ],
    }


def test_convert_points_success(points_geojson):
    geojson_content = json.dumps(points_geojson).encode('utf-8')
    response = client.post(
        "/convert",
        files={"file": ("points.json", geojson_content, "application/json")},
        data={"name": "test_points", "format": "shp"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    
    # Check if the zip file is valid and contains the expected files
    zip_buffer = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, 'r') as zf:
        assert set(zf.namelist()) == {'test_points.shp', 'test_points.shx', 'test_points.dbf', 'test_points.prj'}

def test_convert_points_to_gpkg_success(points_geojson):
    geojson_content = json.dumps(points_geojson).encode('utf-8')
    response = client.post(
        "/convert",
        files={"file": ("points.json", geojson_content, "application/json")},
        data={"name": "test_points_gpkg", "format": "gpkg"}
    )
    assert response.status_code == 200
    # Recommended MIME type, could also be application/octet-stream
    assert response.headers["content-type"] == "application/geopackage+sqlite3"
    assert response.headers["content-disposition"] == 'attachment; filename="test_points_gpkg.gpkg"'
    # Further validation could involve trying to open the GPKG file with Fiona or GDAL
    # For now, we'll assume a 200 OK and correct headers mean success.
    # To do more:
    # import fiona
    # with fiona.BytesCollection(response.content) as source:
    #     assert len(source) == 1
    #     # Check CRS, schema, etc.

def test_convert_mixed_polygons_success(mixed_polygons_geojson):
    geojson_content = json.dumps(mixed_polygons_geojson).encode('utf-8')
    response = client.post(
        "/convert",
        files={"file": ("mixed.json", geojson_content, "application/json")},
        data={"name": "test_mixed_polygons", "format": "shp"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    
    zip_buffer = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, 'r') as zf:
        assert set(zf.namelist()) == {'test_mixed_polygons.shp', 'test_mixed_polygons.shx', 'test_mixed_polygons.dbf', 'test_mixed_polygons.prj'}

def test_convert_mixed_polygons_to_gpkg_success(mixed_polygons_geojson):
    geojson_content = json.dumps(mixed_polygons_geojson).encode('utf-8')
    response = client.post(
        "/convert",
        files={"file": ("mixed.json", geojson_content, "application/json")},
        data={"name": "test_mixed_polygons_gpkg", "format": "gpkg"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/geopackage+sqlite3"
    assert response.headers["content-disposition"] == 'attachment; filename="test_mixed_polygons_gpkg.gpkg"'
    # As above, further validation of the GPKG content could be added.

def test_convert_invalid_geojson():
    geojson_content = json.dumps({"type": "Invalid"}).encode('utf-8')
    response = client.post(
        "/convert",
        files={"file": ("invalid.json", geojson_content, "application/json")},
        data={"name": "test_invalid", "format": "shp"}
    )
    assert response.status_code == 400
    # New error message from process_conversion when no features found
    assert "No features with geometry found" in response.json()["detail"]

def test_convert_invalid_name(points_geojson):
    geojson_content = json.dumps(points_geojson).encode('utf-8')
    response = client.post(
        "/convert",
        files={"file": ("points.json", geojson_content, "application/json")},
        data={"name": "../invalid_name", "format": "shp"}
    )
    assert response.status_code == 400
    assert "Invalid name" in response.json()["detail"]

def test_convert_invalid_format(points_geojson):
    geojson_content = json.dumps(points_geojson).encode('utf-8')
    response = client.post(
        "/convert",
        files={"file": ("points.json", geojson_content, "application/json")},
        data={"name": "test_invalid_format", "format": "invalid_format"}
    )
    assert response.status_code == 422 # FastAPI's validation error for Literal

def test_convert_no_features():
    geojson_content = json.dumps({"type": "FeatureCollection", "features": []}).encode('utf-8')
    response = client.post(
        "/convert",
        files={"file": ("no_features.json", geojson_content, "application/json")},
        data={"name": "no_features", "format": "shp"}
    )
    assert response.status_code == 400
    assert "No features with geometry found" in response.json()["detail"]

def test_convert_unsupported_geometry():
    geojson = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": {"type": "GeometryCollection", "geometries": []}, "properties": {}}]
    }
    geojson_content = json.dumps(geojson).encode('utf-8')
    response = client.post(
        "/convert",
        files={"file": ("unsupported.json", geojson_content, "application/json")},
        data={"name": "unsupported", "format": "shp"}
    )
    assert response.status_code == 400
    # Error message changed
    assert "Unsupported geometry type" in response.json()["detail"] or "No features with geometry found" in response.json()["detail"]

def test_convert_mismatched_geometries(mixed_incompatible_geojson):
    # The test expects a valid zip because the first feature (Point) is processed, and the second (Polygon) is skipped.
    geojson_content = json.dumps(mixed_incompatible_geojson).encode('utf-8')
    response = client.post(
        "/convert",
        files={"file": ("mismatched.json", geojson_content, "application/json")},
        data={"name": "mismatched", "format": "shp"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    
    zip_buffer = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, 'r') as zf:
        # We expect a valid shapefile for the points, as polygons will be skipped.
        assert set(zf.namelist()) == {'mismatched.shp', 'mismatched.shx', 'mismatched.dbf', 'mismatched.prj'} 