# fichero-engine scripts

Repository automation scripts for the Fichero Python backend.

## Development

| Script | Purpose |
|---|---|
| `start_backend.sh` | Start API server for local development |
| `start_backend.py` | Python entry point for bundled backend (Briefcase) |
| `sync_openapi_schema.sh` | Export Python OpenAPI schema → Swift client. **Run after any API change.** |
| `generate_openapi_cli.py` | Regenerate the typed CLI surface (called by `sync_openapi_schema.sh`) |
| `seed_test_library.py` | Build the shared deterministic `.fichero` fixture used by Python + Swift integration harnesses |

## Validation

| Script | Purpose |
|---|---|
| `validate_model_sync.py` | Verify Python/Swift model field alignment (called by `start_backend.sh`) |
| `export_openapi_schema.py` | Raw schema export (called by `sync_openapi_schema.sh`) |

## Build and packaging

| Script | Purpose |
|---|---|
| `build_backend_bundle.sh` | Build Briefcase macOS bundle |
| `xcode_copy_backend.sh` | Xcode build-phase helper — copies bundle into app resources |

## Utilities

| Script | Purpose |
|---|---|
| `clean_local_artifacts.sh` | Remove build artifacts, caches, and generated files |

## Docs-only / stale candidates

These still exist in the tree, but current code references suggest they are not part of
the supported day-to-day flow:

| Script | Current status |
|---|---|
| `bundle_python_backend.sh` | Alternate packaging path; stale candidate pending follow-up removal review |
| `validate_repo.sh` | Older heavyweight local gate script; stale candidate pending follow-up review |

## When to run sync

Run `./fichero-engine/scripts/sync_openapi_schema.sh` after modifying:
- Any route in `src/fichero/api/routes/`
- Any Pydantic model in `src/fichero/models.py` or related model files
- Request/response schemas
