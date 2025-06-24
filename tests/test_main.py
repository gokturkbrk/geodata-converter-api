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
    response = client.post(
        "/convert",
        json={"geojson": points_geojson, "name": "test_points"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    
    # Check if the zip file is valid and contains the expected files
    zip_buffer = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, 'r') as zf:
        assert set(zf.namelist()) == {'test_points.shp', 'test_points.shx', 'test_points.dbf', 'test_points.prj'}

def test_convert_mixed_polygons_success(mixed_polygons_geojson):
    response = client.post(
        "/convert",
        json={"geojson": mixed_polygons_geojson, "name": "test_mixed_polygons"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    
    zip_buffer = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, 'r') as zf:
        assert set(zf.namelist()) == {'test_mixed_polygons.shp', 'test_mixed_polygons.shx', 'test_mixed_polygons.dbf', 'test_mixed_polygons.prj'}

def test_convert_invalid_geojson():
    response = client.post(
        "/convert",
        json={"geojson": {"type": "Invalid"}, "name": "test_invalid"},
    )
    assert response.status_code == 400
    assert "Invalid GeoJSON" in response.json()["detail"]

def test_convert_invalid_name(points_geojson):
    response = client.post(
        "/convert",
        json={"geojson": points_geojson, "name": "../invalid_name"},
    )
    assert response.status_code == 400
    assert "Invalid name" in response.json()["detail"]

def test_convert_no_features():
    response = client.post(
        "/convert",
        json={"geojson": {"type": "FeatureCollection", "features": []}, "name": "no_features"},
    )
    assert response.status_code == 400
    assert "GeoJSON has no features" in response.json()["detail"]

def test_convert_unsupported_geometry():
    geojson = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": {"type": "GeometryCollection", "geometries": []}, "properties": {}}]
    }
    response = client.post(
        "/convert",
        json={"geojson": geojson, "name": "unsupported"},
    )
    assert response.status_code == 400
    assert "No processable features" in response.json()["detail"]

def test_convert_mismatched_geometries(mixed_incompatible_geojson):
    # The test expects a valid zip because the first feature (Point) is processed, and the second (Polygon) is skipped.
    response = client.post(
        "/convert",
        json={"geojson": mixed_incompatible_geojson, "name": "mismatched"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    
    zip_buffer = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, 'r') as zf:
        # We expect a valid shapefile for the points, as polygons will be skipped.
        assert set(zf.namelist()) == {'mismatched.shp', 'mismatched.shx', 'mismatched.dbf', 'mismatched.prj'} 