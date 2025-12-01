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
import ijson
from decimal import Decimal
from fiona.crs import from_epsg
from fastapi import BackgroundTasks, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
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

# WGS84 projection .prj file content
WGS84_PRJ = 'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",' \
            'SPHEROID["WGS_1984",6378137,298.257223563]],' \
            'PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]'

logging.basicConfig(level=logging.INFO)

def cleanup_temp_dir(temp_dir_path: str):
    try:
        shutil.rmtree(temp_dir_path)
        logging.info(f"Successfully cleaned up temp directory: {temp_dir_path}")
    except Exception as e:
        logging.error(f"Error cleaning up temp directory {temp_dir_path}: {e}")

def infer_schema_streaming(input_path: str):
    """
    First pass: Stream through the file to infer schema from all features.
    """
    properties_schema = {}
    
    with open(input_path, 'rb') as f:
        # ijson.items yields objects from the stream. 
        # We assume standard GeoJSON structure: root -> features -> item
        features = ijson.items(f, 'features.item')
        for feature in features:
            props = feature.get('properties')
            if not props:
                continue
            for key, value in props.items():
                if value is None:
                    continue
                
                # Normalize type
                val_type = type(value)
                if val_type == bool:
                    val_type = int
                elif val_type == Decimal:
                    val_type = float
                
                current_type = properties_schema.get(key)
                
                if current_type is None:
                    properties_schema[key] = val_type
                elif current_type == val_type:
                    continue
                elif {current_type, val_type} <= {int, float}:
                    properties_schema[key] = float
                else:
                    properties_schema[key] = str
                    
    return properties_schema

def process_conversion(temp_dir: str, input_geojson_path: str, name: str, output_format: str):
    """
    Synchronous function to handle the CPU-bound conversion process.
    """
    # 1. Infer Schema (Pass 1)
    properties_schema = infer_schema_streaming(input_geojson_path)
    
    # We need to get the first geometry type to validate consistency
    # We can do this by peeking or just checking during the second pass.
    # For simplicity and efficiency, let's start the second pass.
    
    if output_format == 'shp':
        shapefile_path = os.path.join(temp_dir, name)
        
        # We need to determine the shape type before opening the writer.
        # Let's scan for the first valid geometry.
        first_geom_type = None
        with open(input_geojson_path, 'rb') as f:
            features = ijson.items(f, 'features.item')
            for feature in features:
                geom = feature.get('geometry')
                if geom and geom.get('type'):
                    first_geom_type = geom.get('type')
                    break
        
        if not first_geom_type:
            raise fastapi.HTTPException(status_code=400, detail="No features with geometry found.")

        shapetype_map = {
            "Point": shapefile.POINT,
            "MultiPoint": shapefile.MULTIPOINT,
            "LineString": shapefile.POLYLINE,
            "MultiLineString": shapefile.POLYLINE, # Flattened
            "Polygon": shapefile.POLYGON,
            "MultiPolygon": shapefile.POLYGON, # Flattened
        }
        
        # Handle flattening logic mapping
        # If it's MultiPolygon, we treat it as Polygon for the shapefile type, 
        # but we must flatten the features later.
        base_geom_type = first_geom_type
        if base_geom_type == 'MultiPolygon':
            base_geom_type = 'Polygon'
        elif base_geom_type == 'MultiLineString':
            base_geom_type = 'LineString'

        shape_type = shapetype_map.get(base_geom_type)
        if shape_type is None:
            raise fastapi.HTTPException(status_code=400, detail=f"Unsupported geometry type: {first_geom_type}")

        with shapefile.Writer(shapefile_path, shapeType=shape_type) as w:
            # Define fields
            field_names = []
            seen_fields = set()
            
            for key, val_type in properties_schema.items():
                # Handle 10 char limit and uniqueness
                base_name = key[:10]
                final_name = base_name
                counter = 1
                while final_name in seen_fields:
                    suffix = str(counter)
                    final_name = base_name[:10-len(suffix)] + suffix
                    counter += 1
                
                seen_fields.add(final_name)
                field_names.append(key)

                if val_type == int:
                    w.field(final_name, 'N')
                elif val_type == float:
                    w.field(final_name, 'F', size=18, decimal=10)
                else:
                    w.field(final_name, 'C', size=254)

            # Pass 2: Write features
            with open(input_geojson_path, 'rb') as f:
                features = ijson.items(f, 'features.item')
                for feature in features:
                    geom = feature.get('geometry')
                    if not geom:
                        continue
                        
                    geom_type = geom.get('type')
                    coordinates = geom.get('coordinates')
                    props = feature.get('properties', {})

                    # Flattening Logic
                    features_to_write = []
                    if geom_type == 'MultiPolygon':
                        for poly_coords in coordinates:
                            features_to_write.append({
                                'type': 'Feature',
                                'geometry': {'type': 'Polygon', 'coordinates': poly_coords},
                                'properties': props
                            })
                    elif geom_type == 'MultiLineString':
                        for line_coords in coordinates:
                            features_to_write.append({
                                'type': 'Feature',
                                'geometry': {'type': 'LineString', 'coordinates': line_coords},
                                'properties': props
                            })
                    else:
                        features_to_write.append(feature)

                    for feat in features_to_write:
                        f_geom = feat.get('geometry')
                        f_props = feat.get('properties', {})
                        
                        # Check geometry match (using base type)
                        f_type = f_geom.get('type')
                        if f_type != base_geom_type:
                            logging.warning(f"Skipping feature with mismatched geometry: {f_type} (expected {base_geom_type})")
                            continue

                        w.shape(f_geom)
                        
                        record_values = []
                        for key in field_names:
                            val = f_props.get(key)
                            if val is None:
                                record_values.append(None)
                            elif properties_schema[key] == int and isinstance(val, bool):
                                record_values.append(int(val))
                            else:
                                record_values.append(val)
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
        return zip_buffer, "application/zip", f"{name}.zip"

    elif output_format == 'gpkg':
        gpkg_path = os.path.join(temp_dir, f"{name}.gpkg")
        
        # Determine geometry type from first valid feature
        first_geom_type = None
        with open(input_geojson_path, 'rb') as f:
            features = ijson.items(f, 'features.item')
            for feature in features:
                geom = feature.get('geometry')
                if geom and geom.get('type'):
                    first_geom_type = geom.get('type')
                    break
        
        if not first_geom_type:
            raise fastapi.HTTPException(status_code=400, detail="No features with geometry found.")

        # Flattening logic implies we target the single type
        target_geom_type = first_geom_type
        if target_geom_type == 'MultiPolygon':
            target_geom_type = 'Polygon'
        elif target_geom_type == 'MultiLineString':
            target_geom_type = 'LineString'

        schema = {
            'geometry': target_geom_type,
            'properties': {}
        }
        
        type_mapping = {
            str: 'str',
            int: 'int',
            float: 'float',
            bool: 'int'
        }
        
        for key, val_type in properties_schema.items():
            schema['properties'][key] = type_mapping.get(val_type, 'str')

        with fiona.open(gpkg_path, 'w', driver='GPKG', schema=schema, crs=from_epsg(4326)) as sink:
             with open(input_geojson_path, 'rb') as f:
                features = ijson.items(f, 'features.item')
                for feature in features:
                    geom = feature.get('geometry')
                    if not geom: continue
                    
                    geom_type = geom.get('type')
                    coordinates = geom.get('coordinates')
                    props = feature.get('properties', {})

                    features_to_write = []
                    if geom_type == 'MultiPolygon':
                        for poly_coords in coordinates:
                            features_to_write.append({
                                'type': 'Feature',
                                'geometry': {'type': 'Polygon', 'coordinates': poly_coords},
                                'properties': props
                            })
                    elif geom_type == 'MultiLineString':
                        for line_coords in coordinates:
                            features_to_write.append({
                                'type': 'Feature',
                                'geometry': {'type': 'LineString', 'coordinates': line_coords},
                                'properties': props
                            })
                    else:
                        features_to_write.append(feature)

                    for feat in features_to_write:
                        # Validate geometry type matches schema
                        if feat['geometry']['type'] != target_geom_type:
                            continue
                        
                        # Convert bools
                        if 'properties' in feat:
                            feat['properties'] = {k: (int(v) if isinstance(v, bool) else v) for k, v in feat['properties'].items()}
                        
                        try:
                            sink.write(feat)
                        except Exception as e:
                            logging.warning(f"Skipping feature due to write error: {e}")

        return gpkg_path, "application/geopackage+sqlite3", f"{name}.gpkg"


@app.post("/convert")
async def convert_geojson(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: str = Form(...),
    format: Literal['shp', 'gpkg'] = Form('shp')
):
    if "/" in name or "\\" in name or ".." in name:
        raise fastapi.HTTPException(status_code=400, detail="Invalid name.")

    temp_dir = tempfile.mkdtemp()
    input_geojson_path = os.path.join(temp_dir, "input.geojson")
    
    try:
        # Stream upload to temp file
        with open(input_geojson_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Offload CPU-bound conversion to threadpool
        result = await run_in_threadpool(process_conversion, temp_dir, input_geojson_path, name, format)
        
        content, media_type, filename = result
        
        # If result is a path (GPKG), return FileResponse
        if isinstance(content, str):
             background_tasks.add_task(cleanup_temp_dir, temp_dir)
             return FileResponse(
                content,
                media_type=media_type,
                filename=filename,
                background=background_tasks
            )
        else:
            # If result is bytes buffer (Zip), return StreamingResponse
            background_tasks.add_task(cleanup_temp_dir, temp_dir)
            return StreamingResponse(
                content,
                media_type=media_type,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
                background=background_tasks
            )

    except fastapi.HTTPException as e:
        cleanup_temp_dir(temp_dir)
        raise e
    except Exception as e:
        cleanup_temp_dir(temp_dir)
        logging.error(f"Error: {e}")
        raise fastapi.HTTPException(status_code=500, detail=str(e))