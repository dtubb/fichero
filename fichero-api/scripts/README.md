# fichero-api scripts

Repository automation scripts for the Fichero Python backend.

## Development

| Script | Purpose |
|---|---|
| `start_backend.sh` | Start API server for local development |
| `start_backend.py` | Python entry point for bundled backend (Briefcase) |
| `sync_openapi_schema.sh` | Export Python OpenAPI schema → Swift client. **Run after any API change.** |

## Validation

| Script | Purpose |
|---|---|
| `validate_repo.sh` | Run tests, lint, and checks |
| `validate_model_sync.py` | Verify Python/Swift model field alignment (called by `start_backend.sh`) |
| `export_openapi_schema.py` | Raw schema export (called by `sync_openapi_schema.sh`) |
| `run_migration.py` | Knowledge graph migration CLI with dry-run/rollback support |

## Build and packaging

| Script | Purpose |
|---|---|
| `build_backend_bundle.sh` | Build Briefcase macOS bundle |
| `bundle_python_backend.sh` | Package Python backend artifacts (called by build script) |
| `xcode_copy_backend.sh` | Xcode build-phase helper — copies bundle into app resources |

## Utilities

| Script | Purpose |
|---|---|
| `clean_local_artifacts.sh` | Remove build artifacts, caches, and generated files |

## When to run sync

Run `./fichero-api/scripts/sync_openapi_schema.sh` after modifying:
- Any route in `src/fichero/api/routes/`
- Any Pydantic model in `src/fichero/models.py` or related model files
- Request/response schemas
