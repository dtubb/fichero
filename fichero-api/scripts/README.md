# fichero-api scripts

All repository automation scripts live in this folder.

## Core local development
- `start_backend.sh`: Start API server with project defaults.
- `start_backend.py`: Python entry for local backend start flow.
- `sync_openapi_schema.sh`: Export backend OpenAPI schema and copy it into `fichero-swiftui/fichero-api-client`.

## Validation and checks
- `validate_repo.sh`: Run repository validation commands.
- `validate_model_sync.py`: Verify backend models and generated schema alignment.
- `validate_swift_api_calls.py`: Validate Swift client API call usage against schema.
- `verify_system.py`: End-to-end environment verification helper.
- `check_dependencies.py`: Report missing or inconsistent Python dependencies.

## Build and packaging
- `build_backend_bundle.sh`: Build bundled backend app via Briefcase.
- `build_dual_backend.sh`: Build backend bundle variants.
- `bundle_python_backend.sh`: Package Python backend artifacts.
- `xcode_copy_backend.sh`: Xcode build-phase helper to copy bundled backend into app resources.

## Utilities
- `clean_local_artifacts.sh`: Remove local generated artifacts and caches.
- `export_api_schemas.py`: Export API schemas for tooling/docs.
- `export_openapi_schema.py`: Export OpenAPI schema JSON used by Swift client sync.
- `refresh_app_icon.sh`: Refresh app icon assets.
- `setup_app_icon.py`: Generate/setup icon asset inputs.

## Ownership boundary
- Backend schema source of truth: `fichero-api/src/fichero/...`
- Swift package consumer: `fichero-swiftui/fichero-api-client`
- When backend API routes or schema models change, run:
  - `./fichero-api/scripts/sync_openapi_schema.sh`
