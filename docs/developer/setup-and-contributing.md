# Setup and Contributing

## Table of Contents

- [Local Development Commands](#local-development-commands)
- [Backend First](#backend-first)
- [OpenAPI Sync Discipline](#openapi-sync-discipline)
- [Verification Expectations](#verification-expectations)

## Local Development Commands

The commands below are the current repo-standard ones from `AGENTS.md` and `.claude/CLAUDE.md`.

### Backend

```bash
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765
PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived
```

### Swift

```bash
swiftlint lint fichero/fichero/
```

### OpenAPI Sync

```bash
./fichero-engine/scripts/sync_openapi_schema.sh
```

## Backend First

The frontend depends on the local engine being available. For normal app development:

1. start the backend on port `8765`
2. open `fichero/fichero.xcodeproj`
3. build and run the macOS app against that engine

This is the default mental model for the project. The app is not designed as a separate disconnected client.

## OpenAPI Sync Discipline

Any backend API change should trigger a contract check:

- Did the Pydantic model change?
- Did the route signature change?
- Does Swift need regenerated types?
- Do service wrappers need updating?

If the answer is yes, regenerate immediately. Do not leave the frontend and backend out of sync while continuing unrelated work.

## Verification Expectations

This repo distinguishes between worker-level and integrator-level verification.

Worker-level expectations:

- lint the area you changed
- run focused tests for the touched backend area
- commit small, isolated increments

Manager or integrator expectations:

- build the Xcode project
- run the full `FicheroTests` suite
- verify the cross-stack gate with the backend running

One more repo-specific rule matters for API work: if you change the backend API, you must commit the regenerated client-facing contract artifacts in the same change set so the Swift side stays buildable.
