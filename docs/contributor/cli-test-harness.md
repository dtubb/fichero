(AI generated. Not reviewed.)

# CLI as Backend Test Harness

Use the typed `fichero` CLI to prove backend behavior before blaming SwiftUI.
The CLI mirrors the FastAPI surface and exercises the same OpenAPI contract, auth
headers, library-path header, and response schemas that the app relies on.

## Rule of thumb

If a feature fails in SwiftUI, reproduce the same operation with `python -m
fichero` against the running engine.

- If the CLI fails the same way, the backend or contract owns the bug.
- If the CLI succeeds, inspect the Swift store/service/view wiring.
- If an endpoint is not reachable from the CLI, that is an API-surface gap to
  track in the endpoint coverage matrix.

## Setup

Start the backend from the repo root:

```bash
PYTHONPATH=fichero-server/src ~/.venv/bin/python -m fichero_cli engine start --port 8765
```

Then run CLI commands in another shell. Prefer JSON output for bug reports and
agent comparisons:

```bash
PYTHONPATH=fichero-server/src ~/.venv/bin/python -m fichero_cli --json health
```

## Authentication

The CLI now has a real multi-user auth flow:

```bash
PYTHONPATH=fichero-server/src .venv/bin/python -m fichero_cli auth login
PYTHONPATH=fichero-server/src .venv/bin/python -m fichero_cli auth whoami
PYTHONPATH=fichero-server/src .venv/bin/python -m fichero_cli auth logout
```

Credential resolution is:

1. `FICHERO_SESSION_TOKEN`
2. `~/Library/Application Support/Fichero/cli-session.json`
3. `FICHERO_API_KEY`
4. `~/Library/Application Support/Fichero/.api-key`

`auth login` writes `cli-session.json` with mode `0600`. That session token is
preferred over the bootstrap/shared-secret fallback so normal CLI use does not
quietly keep running as the bootstrap owner after a real user logs in.

Common auth failures:

- `401` means the token is missing or expired. Run `fichero auth login`.
- `403` means the current user is authenticated but does not have access to the
  selected library. Re-check `--library` / `FICHERO_LIBRARY_PATH` and the ACL.

For library-scoped endpoints, pass the same library the app is using:

```bash
PYTHONPATH=fichero-server/src ~/.venv/bin/python -m fichero_cli \
  --library /path/to/Library.fichero \
  --json search "sample query"
```

## Importers Need The Engine

`import-manifest` and `import-iiif` are thin HTTP clients. They do not write the
library directly; they call the running engine's `/api/library`, `/api/documents`,
`/api/entities`, and related routes.

That means:

- start the engine first
- pass `--api` only when you are targeting a non-default engine URL
- let the importer reuse the same CLI auth/session token resolution unless you
  explicitly pass `--token-file`

Example:

```bash
bash fichero-server/scripts/start_backend.sh
PYTHONPATH=fichero-server/src .venv/bin/python -m fichero_cli auth login
PYTHONPATH=fichero-server/src .venv/bin/python -m fichero_cli import-manifest \
  --manifest /path/to/manifest.jsonl \
  --library /path/to/Library.fichero
```

## Debug loop

1. Reproduce the action in the UI and note the endpoint, document id, library,
   and visible failure.
2. Run the equivalent CLI command with `--json` and the same `--library-path`.
3. Compare status, payload shape, and returned ids against the UI state.
4. If the backend route changed, regenerate/sync OpenAPI before committing:

```bash
./fichero-server/scripts/sync_openapi_schema.sh
```

5. Add a focused backend unit/integration test or CLI contract test for the
   failure before closing the issue.

## Guardrails

These checks keep the CLI and app from drifting away from the backend contract:

```bash
python3 scripts/check_endpoint_usage.py
python3 scripts/check_endpoint_coverage_matrix.py
PYTHONPATH=fichero-server/src ~/.venv/bin/python fichero-server/scripts/validate_model_sync.py
```

`scripts/verify_all.sh --fast` runs the endpoint and OpenAPI guardrails as part
of the normal manager/integrator gate.
