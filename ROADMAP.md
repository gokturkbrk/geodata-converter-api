# Project Roadmap

This document outlines the development roadmap for the `geojson2shp-api` project, prioritized by impact on stability, security, and functionality.

## 1. Critical Bug Fixes & Stability

### Fix Schema Inference (Completed)
- **Problem**: Currently, the output schema (fields) is determined solely by the *first* feature in the GeoJSON. If subsequent features have fields that the first one doesn't, those fields are silently dropped.
- **Solution**: Implement a two-pass approach:
    1.  Iterate through all features to collect a superset of all properties and their types.
    2.  Write the output file using this unified schema.
- **Status**: ✅ **Fixed**. Implemented two-pass schema inference.

### Robust Geometry Validation (Medium Priority)
- **Problem**: The converter assumes all features match the geometry type of the first feature. Mismatched geometries are skipped/logged but this behavior might be too aggressive for some users.
- **Solution**:
    - Add a `strict` mode flag (default `True`) to error on mismatch.
    - Improve logging to explicitly list skipped feature IDs.
    - Consider supporting multi-layer output for GPKG (one layer per geometry type).

## 2. Security Improvements

### Configurable CORS (High Priority)
- **Problem**: CORS origins are hardcoded to `http://localhost:5173`.
- **Solution**: Load allowed origins from an environment variable (e.g., `ALLOWED_ORIGINS=http://example.com,http://localhost:3000`).
- **Benefit**: Allows safe deployment in different environments without code changes.

### Input Size Limits (Medium Priority)
- **Problem**: Large GeoJSON payloads could cause memory exhaustion (DoS).
- **Solution**: Configure Nginx/Reverse Proxy limits or implement middleware to reject payloads exceeding a certain size (e.g., 50MB).

## 3. Enhancements & Performance

### Non-Blocking I/O (Completed)
- **Problem**: `shapefile` and `fiona` writes are synchronous and blocking. This blocks the main thread of the FastAPI application, making it unresponsive to other requests during large conversions.
- **Solution**: Refactored to use `run_in_threadpool` for CPU-bound conversion tasks.
- **Status**: ✅ **Fixed**. Conversion now runs in a thread pool, keeping the main event loop responsive.

### Docker Optimization (Low Priority)
- **Problem**: Current Dockerfile might be using a heavy base image or not utilizing build stages.
- **Solution**: Use a multi-stage build to reduce final image size and remove build dependencies.

### Code Refactoring (Low Priority)
- **Problem**: `main.py` contains all logic (routes, validation, conversion).
- **Solution**: Refactor into:
    - `app/routers/convert.py`
    - `app/services/converter.py`
    - `app/schemas.py`
- **Benefit**: Improved maintainability and testability.
