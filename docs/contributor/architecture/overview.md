<!-- Verified against api/main.py (_is_allowed_library_path), db_manager.py, FicheroClient.swift (2026-07-18). -->

# Fichero Architecture Overview

Fichero is a two-part system:

- `fichero/`: native macOS SwiftUI app (UI/client)
- `fichero-server/`: Python FastAPI backend (API/workflows/storage/AI)

## Runtime model

```text
fichero (SwiftUI app)
    -> HTTPS (127.0.0.1:8765, loopback-only, cert-pinned)
fichero-server (FastAPI)
    -> DuckDB + LanceDB
    -> workflow engine + tools
    -> LLM providers
```

## Library and Data Locations

Fichero libraries are `.fichero` package directories. The backend accepts
library paths only under the allowlisted user-data roots:

- `~/Documents`, `~/Desktop`, `~/Fichero`
- `~/Dropbox`, `~/code`
- `~/Library/Application Support`, `~/Library/CloudStorage`
- `~/Library/Mobile Documents/com~apple~CloudDocs` for iCloud Drive and
  iCloud-synced Desktop/Documents
- OS temp roots (`/tmp`, `/private/tmp`, `/var/folders`, `/private/var/folders`)
  used by CI and local pytest
- any roots listed in `FICHERO_LIBRARY_ALLOWED_ROOTS` (os.pathsep-separated),
  plus folders the app has granted via a security-scoped bookmark

(The authoritative list is `_is_allowed_library_path` in `fichero-server/src/fichero_server/api/main.py`.)

The `.fichero` suffix is still required. When Desktop/Documents are synced to
iCloud, macOS may expose `~/Documents` as a symlink into Mobile Documents; the
allowlist checks both the expanded path and the resolved path so real user
libraries in `~/Documents/Fichero` continue to open.

Inside a library package, DuckDB lives at `fichero.duckdb` and vector data lives
under `vectors/`. These are real user data once Daniel is working against live
libraries, so repair schema/index problems with idempotent migrations rather
than deleting databases.

## Canonical architecture docs

- Audited mutation path / action registry: `docs/contributor/architecture/action_layer.md`
- API/backend architecture: `docs/contributor/architecture/fichero-server/overview.md`
- AI infrastructure and model policy: `docs/contributor/architecture/ai_infrastructure.md`
- Image editing backend strategy: `docs/contributor/architecture/image_editing_backend_strategy.md`
- Pi in-app agent harness: `docs/contributor/architecture/pi_agent_harness.md`
- MLX/on-device agent service boundary: `docs/contributor/architecture/mlx_on_device_agent.md`
- Workflow multi-pass engine primitives: `docs/contributor/architecture/workflow_multi_pass_engine.md`
- SwiftUI/frontend architecture: `docs/contributor/architecture/fichero/overview.md`
- SwiftUI principles: `docs/contributor/swiftui-principles.md`

## Local run

```bash
# repo root
PYTHONPATH=fichero-server/src .venv/bin/uvicorn fichero_server.api.main:app --port 8765
open fichero/fichero.xcodeproj
```
