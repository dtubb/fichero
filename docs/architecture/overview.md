# Fichero Architecture Overview

Fichero is a two-part system:

- `fichero-swiftui/`: native macOS SwiftUI app (UI/client)
- `fichero-api/`: Python FastAPI backend (API/workflows/storage/AI)

## Runtime model

```text
fichero-swiftui (SwiftUI app)
    -> HTTP (localhost:8765)
fichero-api (FastAPI)
    -> DuckDB + LanceDB
    -> workflow engine + tools
    -> LLM providers
```

## Canonical architecture docs

- API/backend architecture: `docs/architecture/api/overview.md`
- SwiftUI/frontend architecture: `docs/architecture/swiftui/overview.md`
- SwiftUI principles: `docs/architecture/swiftui/SWIFTUI_PRINCIPLES.md`

## Local run

```bash
# repo root
PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765
open fichero-swiftui/fichero-swiftui.xcodeproj
```
