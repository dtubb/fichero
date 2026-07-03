# Fichero Architecture Overview

Fichero is a two-part system:

- `fichero/`: native macOS SwiftUI app (UI/client)
- `fichero-engine/`: Python FastAPI backend (API/workflows/storage/AI)

## Runtime model

```text
fichero (SwiftUI app)
    -> HTTP (localhost:8765)
fichero-engine (FastAPI)
    -> DuckDB + LanceDB
    -> workflow engine + tools
    -> LLM providers
```

## Library and Data Locations

Fichero libraries are `.fichero` package directories. The backend accepts
library paths only under the allowlisted user-data roots:

- `~/Documents`
- `~/Desktop`
- `~/Dropbox`
- `~/Library/Application Support`
- `~/Library/Mobile Documents/com~apple~CloudDocs` for iCloud Drive and
  iCloud-synced Desktop/Documents
- test/temp roots used by CI and local pytest

The `.fichero` suffix is still required. When Desktop/Documents are synced to
iCloud, macOS may expose `~/Documents` as a symlink into Mobile Documents; the
allowlist checks both the expanded path and the resolved path so real user
libraries in `~/Documents/Fichero` continue to open.

Inside a library package, DuckDB lives at `fichero.duckdb` and vector data lives
under `vectors/`. These are real user data once Daniel is working against live
libraries, so repair schema/index problems with idempotent migrations rather
than deleting databases.

## Canonical architecture docs

- Audited mutation path / action registry: `docs/architecture/action_layer.md`
- API/backend architecture: `docs/architecture/api/overview.md`
- AI infrastructure and model policy: `docs/architecture/ai_infrastructure.md`
- Image editing backend strategy: `docs/architecture/image_editing_backend_strategy.md`
- Pi in-app agent harness: `docs/architecture/pi_agent_harness.md`
- MLX/on-device agent service boundary: `docs/architecture/mlx_on_device_agent.md`
- Workflow multi-pass engine primitives: `docs/architecture/workflow_multi_pass_engine.md`
- SwiftUI/frontend architecture: `docs/architecture/swiftui/overview.md`
- SwiftUI principles: `docs/contributor/swiftui-principles.md`

## Local run

```bash
# repo root
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765
open fichero/fichero.xcodeproj
```
