import fastapi
import pydantic
import shapefile
import zipfile
import io
import os
import tempfile
import shutil
import logging
import fiona
from fiona.crs import from_epsg
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Literal

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
    format: Literal['shp', 'gpkg'] = 'shp'

# WGS84 projection .prj file content
WGS84_PRJ = 'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",' \
            'SPHEROID["WGS_1984",6378137,298.257223563]],' \
            'PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]'

logging.basicConfig(level=logging.INFO)

@app.post("/convert")
async def convert_geojson(request: ConversionRequest):
    geojson = request.geojson
    name = request.name
    output_format = request.format

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
        if output_format == 'shp':
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
                raise fastapi.HTTPException(status_code=400, detail=f"Unsupported geometry type for Shapefile: {first_geom_type}")

            with shapefile.Writer(shapefile_path, shapeType=shape_type) as w:
                first_props = features[0].get('properties', {})
                # Define fields based on the properties of the first feature
                field_names = []
                if first_props: # Ensure there are properties to define fields
                    for fname, val in first_props.items():
                        field_names.append(fname)
                        if isinstance(val, int):
                            w.field(fname, 'N')
                        elif isinstance(val, float):
                            w.field(fname, 'F')
                        else:
                            w.field(fname, 'C', size=254)

                for feature in features:
                    geom = feature.get('geometry')
                    props = feature.get('properties', {})

                    if not geom or geom.get('type') != first_geom_type:
                        logging.warning(f"Skipping feature with mismatched geometry for Shapefile: {geom.get('type') if geom else 'None'}")
                        continue

                    w.shape(geom)
                    # Prepare record values, ensuring order matches field_names and handling missing properties
                    record_values = [props.get(fn) for fn in field_names]
                    w.record(*record_values)


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

        elif output_format == 'gpkg':
            gpkg_path = os.path.join(temp_dir, f"{name}.gpkg")

            # Determine schema from the first feature
            first_feature = features[0]
            first_geometry = first_feature.get('geometry', {})
            first_properties = first_feature.get('properties', {})

            if not first_geometry or 'type' not in first_geometry:
                 raise fastapi.HTTPException(status_code=400, detail="First feature has no geometry or geometry type for GPKG.")

            schema = {
                'geometry': first_geometry.get('type'),
                'properties': {k: type(v).__name__ for k, v in first_properties.items()}
            }

            # Replace type names with OGR types for Fiona
            type_mapping = {
                'str': 'str',
                'int': 'int',
                'float': 'float',
                'bool': 'bool'
                # Add other mappings if necessary
            }
            schema['properties'] = {k: type_mapping.get(v, 'str') for k, v in schema['properties'].items()}


            with fiona.open(gpkg_path, 'w', driver='GPKG', schema=schema, crs=from_epsg(4326)) as sink:
                for feature in features:
                    # Ensure feature geometry matches the schema geometry type
                    # This is a simplified check; robust validation might be needed
                    if feature.get('geometry', {}).get('type') == schema['geometry']:
                        try:
                            sink.write(feature)
                        except Exception as e:
                            logging.warning(f"Skipping feature due to fiona write error: {e}. Feature: {feature}")
                    else:
                        logging.warning(f"Skipping feature with mismatched geometry for GPKG: {feature.get('geometry', {}).get('type')}")

            return FileResponse(
                gpkg_path,
                media_type="application/geopackage+sqlite3", # Recommended MIME type
                # media_type="application/octet-stream", # Alternative
                headers={"Content-Disposition": f"attachment; filename={name}.gpkg"}
            )

    except Exception as e:
        logging.error(f"Exception during conversion: {e}")
        # Clean up the temporary directory in case of an early exit due to error
        if os.path.exists(temp_dir):
             shutil.rmtree(temp_dir)
        raise fastapi.HTTPException(status_code=500, detail=f"An error occurred during conversion: {str(e)}")
    finally:
        # Ensure cleanup happens unless an error already removed it or it's a FileResponse case
        # For FileResponse, the file is cleaned up after being sent.
        # A more robust solution for FileResponse cleanup might involve background tasks if not handled by FastAPI.
        if output_format == 'shp' and os.path.exists(temp_dir): # Only clean for shp here, gpkg handled by FileResponse
            shutil.rmtree(temp_dir)
        elif output_format == 'gpkg' and not isinstance(e if 'e' in locals() else None, FileResponse):
            # If it's gpkg and an error occurred before FileResponse, or if FileResponse itself failed.
            # This logic might need refinement depending on how FileResponse handles cleanup on error.
            if os.path.exists(temp_dir): # Check again, as error handling might have already cleaned it.
                shutil.rmtree(temp_dir)