# 12. The CLI as a Test Harness


Use the typed `fichero` CLI to prove backend behavior before blaming SwiftUI. The CLI mirrors the FastAPI surface and exercises the same OpenAPI contract, auth headers, library-path header, and response schemas the app relies on.

Rule of thumb: if a feature fails in SwiftUI, reproduce the same operation with the CLI against the running engine.

- CLI fails the same way → the backend or contract owns the bug.
- CLI succeeds → inspect the Swift store/service/view wiring.
- Endpoint not reachable from the CLI → an API-surface gap to track in the endpoint coverage matrix.

### Setup

The CLI module is `fichero_cli`, and the venv is the repo `.venv` (chapter 10). With it activated, the installed `fichero` entry point works directly; the module form is equivalent:

    # Start the engine
    bash fichero-server/scripts/start_backend.sh

    # In another shell — prefer JSON output for bug reports and comparisons
    PYTHONPATH=fichero-server/src:fichero-cli/src .venv/bin/python -m fichero_cli --json health

Remember the feature-tier trap from chapter 3: a hand-started engine at the default `release` tier 404s the workflow/KG surface. `start_backend.sh` defaults to `dev` tier, which is what you want for CLI exploration.

### Authentication

    PYTHONPATH=fichero-server/src:fichero-cli/src .venv/bin/python -m fichero_cli auth login
    PYTHONPATH=fichero-server/src:fichero-cli/src .venv/bin/python -m fichero_cli auth whoami
    PYTHONPATH=fichero-server/src:fichero-cli/src .venv/bin/python -m fichero_cli auth logout

Credential resolution order:

1.  `FICHERO_SESSION_TOKEN`
2.  `~/Library/Application Support/Fichero/cli-session.json`
3.  `FICHERO_API_KEY`
4.  `~/Library/Application Support/Fichero/.api-key`

`auth login` writes `cli-session.json` with mode `0600`; the session token is preferred over the bootstrap/shared-secret fallback so normal CLI use does not quietly keep running as the bootstrap owner after a real user logs in. A `401` means the token is missing or expired (`auth login`); a `403` means the user is authenticated but lacks access to the selected library — re-check `--library` / `FICHERO_LIBRARY_PATH` and the ACL.

For library-scoped endpoints, pass the same library the app is using with the `--library` flag:

    PYTHONPATH=fichero-server/src:fichero-cli/src .venv/bin/python -m fichero_cli \
      --library "$HOME/Documents/My Library.fichero" \
      --json search "sample query"

### Importers need the engine

`import-manifest` and `import-iiif` are thin HTTP clients over the backend routes — they do not write the library directly. Start the engine first; pass `--api` only when targeting a non-default engine URL; let the importer reuse the CLI auth/session resolution unless you explicitly pass `--token-file`.

    bash fichero-server/scripts/start_backend.sh
    PYTHONPATH=fichero-server/src:fichero-cli/src .venv/bin/python -m fichero_cli auth login
    PYTHONPATH=fichero-server/src:fichero-cli/src .venv/bin/python -m fichero_cli import-manifest \
      --manifest /path/to/manifest.jsonl \
      --library "$HOME/Documents/My Library.fichero"

### Debug loop

1.  Reproduce the action in the UI; note the endpoint, document id, library, and visible failure.
2.  Run the equivalent CLI command with `--json` and the same `--library`.
3.  Compare status, payload shape, and returned ids against UI state.
4.  If the backend route changed, run `./fichero-server/scripts/sync_openapi_schema.sh` before committing.
5.  Add a focused backend unit/integration test or CLI contract test for the failure before closing the issue.

Guardrails that keep the CLI and app from drifting from the contract, all part of `verify_all.sh --fast`:

    python3 scripts/check_endpoint_usage.py
    python3 scripts/check_endpoint_coverage_matrix.py
    PYTHONPATH=fichero-server/src python fichero-server/scripts/validate_model_sync.py
