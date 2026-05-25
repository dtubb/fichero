# STATE.md — Fichero

## Snapshot

**Branch:** `0.0.2`

## Current Focus

Entity Platform and repo hygiene. The repo is verified green. Work the four phases below in order, one phase at a time. After each phase: run the gate, commit, and only then move on.

## In Progress

Nothing. All loops stopped. Working interactively with Claude directly.

Global rules:
- Use jCodemunch MCP for code navigation; read full files only before editing.
- Canonical gate is `bash scripts/verify_all.sh`.
- GitHub Issues is the canonical backlog; commit directly to `0.0.2` with conventional commits that reference the issue.
- Register every new `.swift` file with `ruby scripts/add-swift-file.rb <path>`.
- Never edit generated code (`fichero-api-client` generated sources, `openapi.json`).
- After any backend API change, run `./fichero-engine/scripts/sync_openapi_schema.sh` and commit the regenerated client.

Start of work: read `STATE.md` and `MEMORY.md`, then run `bash scripts/verify_all.sh` to confirm green.

1. **Dependabot high** — bump `liquidjs` ≥ 10.25.7 in `site/` (DoS via circular block
   ref; `cd site && npm audit fix` or add a package.json `overrides`). NOTE: `verify_all.sh`
   does NOT cover `site/` — verify with `cd site && npm audit`. Commit `fix(deps):`.
2. **SwiftLint cleanup in batches** — `swiftlint lint fichero/fichero/` for the LIVE list
   (don't trust a stale cluster list). One cluster (same rule or file) per commit; gate per
   batch. Length-refactors → extract into a `Foo+Bar.swift` extension and **register it with
   `ruby scripts/add-swift-file.rb`**. Do NOT silence via `.swiftlint.yml`. Preserve behavior.
3. **#1201 — verify gate enforces OpenAPI freshness** — in `scripts/verify_python.sh`, after
   the contract walk: regenerate (`sync_openapi_schema.sh`), `git diff` the committed
   `openapi.json` + Swift client, FAIL + `git checkout --` to leave the tree clean if they
   differ (never silently commit a regen). Manually confirm it fails on an unsynced API change.
   Update the AGENTS.md/docs gate note; close #1201.
4. **KG entity library** (this morning's thread — OntologyBrowser / EntityDigestView /
   SpeakerComparison / CLI #1193 are shipped). Next: **#1191** (standalone two-column entity
   digest page) or **#1183** (entity profile view in inspector w/ click-through to PDF) —
   confirm which from the issues + `.superpowers/brainstorm/.../entity-*.html`. Build on the
   existing OntologyBrowser code. Aggregation/scoping/dedup is BACKEND; views only render.

- **Do NOT use cheap OpenRouter cascade for SwiftUI/backend work** — Claude/Codex direct. See MEMORY.md cascade model selection.

## Blocked

- OpenRouter weekly key quota can hard-stop remote vision/extraction runs (`403 Key limit exceeded`) on some libraries.
