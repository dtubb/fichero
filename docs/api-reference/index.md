---
hide:
  - toc
---

# API Reference

The Fichero engine is a FastAPI application that exposes an OpenAPI 3 schema.
The interactive reference below is rendered from the committed schema
(`openapi.json`, copied from `fichero-engine/tests/contracts/openapi.json`).

!!! note
    This is a static render of the committed contract schema, not a live
    connection to a running engine. The engine serves its own live docs at
    `https://127.0.0.1:8765/docs` (Swagger UI) and `/redoc` when running
    locally via `bash fichero-engine/scripts/start_backend.sh`.

<redoc spec-url="openapi.json" hide-download-button></redoc>
<script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
