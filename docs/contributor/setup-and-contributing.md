# Setup and Contributing

## Table of Contents

- [Local Development Commands](#local-development-commands)
- [Backend First](#backend-first)
- [OpenAPI Sync Discipline](#openapi-sync-discipline)
- [Verification Expectations](#verification-expectations)

## Local Development Commands

The commands below are the current repo-standard ones from `AGENTS.md`.

### Backend

```bash
bash fichero-engine/scripts/start_backend.sh
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

The frontend depends on the engine being available. For the default macOS development path:

1. start the backend on port `8765`
   via `bash fichero-engine/scripts/start_backend.sh`
2. open `fichero/fichero.xcodeproj`
3. build and run the macOS app against that engine

This is the default mental model for embedded-macOS development. iOS/iPadOS do not start a local engine; they connect to an explicit remote host configured through `EngineConfig`.

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

## Contributing Mechanics

### New Swift files require registration

The `Fichero` main target uses traditional PBX file references. A `.swift` file written to disk is invisible to the Xcode compiler until it is registered:

```bash
ruby scripts/add-swift-file.rb fichero/fichero/Views/MyFolder/MyView.swift
```

`scripts/add-swift-file.rb` uses the `xcodeproj` Ruby gem (installed at `~/.gem/ruby/2.6.0/gems/xcodeproj-1.27.0/`). Never edit `project.pbxproj` by hand. Test-target files are the exception; those use sync'd groups and are picked up automatically.

### No per-task branches

Commit work directly to the milestone branch. Do not create a branch per issue
or per task. Isolated worktrees live under `~/code/fichero-worktrees/<name>`,
not ad hoc sibling directories.

### Conventional commits with issue references

```
feat: add document tagging endpoint (#420)
fix: resolve entity merge race condition (#388)
chore: bump ruff to 0.4.5
```

Prefixes: `feat`, `fix`, `chore`, `refactor`, `test`, `docs`, `style`. Always include the GitHub issue number when the commit closes or advances one.

### Never push directly to main

All work goes through a PR. Create it and merge it yourself once the build gate passes.

### 0.0.x no-migration rule

Backend schema changes go into `db.py` `_ensure_table` via the Pydantic model field. Fresh databases pick up new columns automatically.

Do not add `ALTER TABLE ADD COLUMN` migration functions for columns that are already declared in the model when you are only targeting fresh databases. Persisted libraries still need idempotent `ALTER` and backfill work in `db_migrations.py` when a new column or structural change must land against real existing data.

### Feature tier

`bash fichero-engine/scripts/start_backend.sh` defaults to `FICHERO_FEATURE_TIER=dev` so local testing shows staged surfaces. Override with `FICHERO_FEATURE_TIER=release` when checking release-tier behavior. If your work is only active under `FICHERO_FEATURE_TIER=dev`, say so in your PR description. Core routes must work in `release` tier.

## Expanding the Action Registry

Not every backend mutation goes through `registry.invoke` today. The action registry is the audited path for the domains that have been folded into it, especially the shared mutation path used by chat tools, App Intents, and undo/audit flows. Many route handlers still persist directly with `db.save(...)`.

When you are extending an action-backed mutation surface, route handlers should look like this:

```python
ctx = ActionContext(actor=request.state.user, origin_window=request.headers.get("X-Window-Id"))
result = registry.invoke(db, "document.tag", {"doc_id": doc_id, "tag": tag}, ctx)
return result
```

If you are adding a new shared, audited mutation, define it as a named action in the registry instead of inventing a parallel path. That gives it an audit record, change-event emission, and an undo hook where the action domain supports inversion.

See [action-registry.md](./action-registry.md) for the full guide: how to define an action, implement invert, write the required tests, and use the generic invocation endpoint.
