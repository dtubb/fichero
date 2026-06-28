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
PYTHONPATH=fichero-engine/src ~/.venv/bin/python -m fichero engine start --port 8765
```

Then run CLI commands in another shell. Prefer JSON output for bug reports and
agent comparisons:

```bash
PYTHONPATH=fichero-engine/src ~/.venv/bin/python -m fichero --json health
```

For library-scoped endpoints, pass the same library the app is using:

```bash
PYTHONPATH=fichero-engine/src ~/.venv/bin/python -m fichero \
  --library /path/to/Library.fichero \
  --json search "sample query"
```

## Debug loop

1. Reproduce the action in the UI and note the endpoint, document id, library,
   and visible failure.
2. Run the equivalent CLI command with `--json` and the same `--library-path`.
3. Compare status, payload shape, and returned ids against the UI state.
4. If the backend route changed, regenerate/sync OpenAPI before committing:

```bash
./fichero-engine/scripts/sync_openapi_schema.sh
```

5. Add a focused backend unit/integration test or CLI contract test for the
   failure before closing the issue.

## Guardrails

These checks keep the CLI and app from drifting away from the backend contract:

```bash
python3 scripts/check_endpoint_usage.py
python3 scripts/check_endpoint_coverage_matrix.py
PYTHONPATH=fichero-engine/src ~/.venv/bin/python fichero-engine/scripts/validate_model_sync.py
```

`scripts/verify_all.sh --fast` runs the endpoint and OpenAPI guardrails as part
of the normal manager/integrator gate.
