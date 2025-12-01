from fastapi.testclient import TestClient
from main import app
import zipfile
import io
import shapefile
import shutil
import json
import os

client = TestClient(app)

def test_schema_inference_heterogeneous_features():
    """
    Test that the converter correctly infers schema from ALL features,
    not just the first one.
    """
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [0, 0]},
                "properties": {"id": 1, "only_in_first": "A"}
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [1, 1]},
                "properties": {"id": 2, "only_in_second": "B"}
            }
        ]
    }

    # 1. Test Shapefile Conversion
    # Prepare GeoJSON file content
    import json
    geojson_content = json.dumps(geojson).encode('utf-8')
    
    response = client.post("/convert", 
        files={"file": ("test.json", geojson_content, "application/json")},
        data={
            "name": "test_schema",
            "format": "shp"
        }
    )
    assert response.status_code == 200
    
    # Verify Shapefile content
    zip_content = io.BytesIO(response.content)
    try:
        with zipfile.ZipFile(zip_content) as zf:
            # Extract to a temp dir to read with pyshp
            zf.extractall("temp_test_shp")
            
            sf = shapefile.Reader("temp_test_shp/test_schema.shp")
            fields = [f[0] for f in sf.fields][1:] # Skip DeletionFlag
            
            # Check if both fields exist
            assert "only_in_fi" in fields or "only_in_first" in fields # truncated
            assert "only_in_se" in fields or "only_in_second" in fields # truncated
            
            records = sf.records()
            assert len(records) == 2
            # Check values
            assert len(records[0]) >= 3 # id, only_in_first, only_in_second
            
            sf.close()
    finally:
        if os.path.exists("temp_test_shp"):
            shutil.rmtree("temp_test_shp")

def test_schema_inference_type_promotion():
    """
    Test that types are promoted correctly (int -> float -> str).
    """
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [0, 0]},
                "properties": {"mixed_num": 1} # int
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [1, 1]},
                "properties": {"mixed_num": 1.5} # float
            },
             {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [2, 2]},
                "properties": {"mixed_str": 10} 
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [3, 3]},
                "properties": {"mixed_str": "string_value"} 
            }
        ]
    }

    import json
    geojson_content = json.dumps(geojson).encode('utf-8')

    response = client.post("/convert", 
        files={"file": ("test.json", geojson_content, "application/json")},
        data={
            "name": "test_types",
            "format": "shp"
        }
    )
    assert response.status_code == 200
    
    zip_content = io.BytesIO(response.content)
    try:
        with zipfile.ZipFile(zip_content) as zf:
            zf.extractall("temp_test_types")
            sf = shapefile.Reader("temp_test_types/test_types.shp")
            
            # Check field types
            # Field structure: (name, type, size, decimal)
            # Type 'N' = number (int/float), 'C' = character (string)
            fields_dict = {f[0]: f[1] for f in sf.fields[1:]}
            
            assert fields_dict.get('mixed_num') == 'N' or fields_dict.get('mixed_num') == 'F'
            assert fields_dict.get('mixed_str') == 'C'
            
            sf.close()
    finally:
        if os.path.exists("temp_test_types"):
            shutil.rmtree("temp_test_types")
