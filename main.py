import fastapi
import pydantic
import shapefile
import zipfile
import io
import os
import tempfile
import shutil
import logging
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

app = fastapi.FastAPI()

origins = [
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConversionRequest(pydantic.BaseModel):
    geojson: dict
    name: str

# WGS84 projection .prj file content
WGS84_PRJ = 'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",' \
            'SPHEROID["WGS_1984",6378137,298.257223563]],' \
            'PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]'

logging.basicConfig(level=logging.INFO)

@app.post("/convert")
async def convert_geojson_to_shp(request: ConversionRequest):
    geojson = request.geojson
    name = request.name

    if not geojson or 'features' not in geojson or not isinstance(geojson['features'], list):
        raise fastapi.HTTPException(status_code=400, detail="Invalid GeoJSON. Must be a FeatureCollection.")

    if not name or not isinstance(name, str) or "/" in name or "\\" in name or ".." in name:
        raise fastapi.HTTPException(status_code=400, detail="Invalid name.")

    features = geojson.get('features', [])
    if not features:
        raise fastapi.HTTPException(status_code=400, detail="GeoJSON has no features.")

    def flatten_features(features):
        flattened = []
        for feature in features:
            geom = feature.get('geometry')
            if not geom:
                continue
            geom_type = geom.get('type')
            coordinates = geom.get('coordinates')
            properties = feature.get('properties')

            if geom_type == 'MultiPolygon':
                for polygon_coords in coordinates:
                    flattened.append({
                        'type': 'Feature',
                        'geometry': {'type': 'Polygon', 'coordinates': polygon_coords},
                        'properties': properties
                    })
            elif geom_type == 'MultiLineString':
                for line_coords in coordinates:
                    flattened.append({
                        'type': 'Feature',
                        'geometry': {'type': 'LineString', 'coordinates': line_coords},
                        'properties': properties
                    })
            elif geom_type in ['Polygon', 'LineString', 'Point', 'MultiPoint']:
                flattened.append(feature)
            else:
                logging.warning(f"Skipped unsupported geometry type: {geom_type}")
        return flattened

    features = flatten_features(features)
    if not features:
        raise fastapi.HTTPException(status_code=400, detail="No processable features found in GeoJSON.")

    temp_dir = tempfile.mkdtemp()
    try:
        shapefile_path = os.path.join(temp_dir, name)
        first_geom_type = features[0].get('geometry', {}).get('type')
        if not first_geom_type:
            raise fastapi.HTTPException(status_code=400, detail="First feature has no geometry type.")

        shapetype_map = {
            "Point": shapefile.POINT,
            "MultiPoint": shapefile.MULTIPOINT,
            "LineString": shapefile.POLYLINE,
            "Polygon": shapefile.POLYGON,
        }
        shape_type = shapetype_map.get(first_geom_type)
        if shape_type is None:
            raise fastapi.HTTPException(status_code=400, detail=f"Unsupported geometry type: {first_geom_type}")

        with shapefile.Writer(shapefile_path, shapeType=shape_type) as w:
            first_props = features[0].get('properties', {})
            for fname, val in first_props.items():
                if isinstance(val, int):
                    w.field(fname, 'N')
                elif isinstance(val, float):
                    w.field(fname, 'F')
                else:
                    w.field(fname, 'C', size=254)
            field_names = list(first_props.keys())

            for feature in features:
                geom = feature.get('geometry')
                props = feature.get('properties', {})

                if not geom or geom.get('type') != first_geom_type:
                    logging.warning(f"Skipping feature with mismatched geometry: {geom.get('type') if geom else 'None'}")
                    continue

                w.shape(geom)
                w.record(*[props.get(fn) for fn in field_names])

        with open(f"{shapefile_path}.prj", "w") as prj_file:
            prj_file.write(WGS84_PRJ)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for ext in ['shp', 'shx', 'dbf', 'prj']:
                filepath = os.path.join(temp_dir, f"{name}.{ext}")
                if os.path.exists(filepath):
                    zf.write(filepath, arcname=f"{name}.{ext}")
        zip_buffer.seek(0)

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={name}.zip"}
        )

    except Exception as e:
        logging.error(f"Exception during shapefile conversion: {e}")
        raise fastapi.HTTPException(status_code=500, detail=f"An error occurred during conversion: {e}")
    finally:
        shutil.rmtree(temp_dir)