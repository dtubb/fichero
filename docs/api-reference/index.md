---
hide:
  - toc
---

# API Reference

!!! warning "Work in progress, unstable"
    The Fichero API is still in progress. Endpoints and response shapes will
    change before 1.0, and this is not yet a stable contract. Do not build
    against it expecting backward compatibility. The API version tracks the
    dated release.

The Fichero engine is a FastAPI application that exposes an OpenAPI 3 schema.
The interactive reference below is rendered from the committed schema
(`openapi.json`, copied from `fichero-engine/tests/contracts/openapi.json`).

!!! note
    This is a static render of the committed contract schema. For live,
    interactive docs against a running engine, start it locally with
    `bash fichero-engine/scripts/start_backend.sh` and open
    `https://127.0.0.1:8765/docs` (Swagger UI) or `/redoc`.

<redoc spec-url="openapi.json" hide-download-button></redoc>
<script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
