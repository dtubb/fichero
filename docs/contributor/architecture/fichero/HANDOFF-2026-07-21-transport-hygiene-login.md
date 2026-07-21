# HANDOFF — 2026-07-21 (transport done → engine hygiene reorg → login)

Fresh-context continuation prompt. Daniel is out running; work autonomously, gate before every push,
commit as the model, update GitHub issues as you go. Serialize heavy jobs (one xcodebuild / one full
pytest at a time). Workers are COMMIT-ONLY; the manager (you) gates.

## Where things stand (all on origin/main)

The **transport architecture is DONE and green on origin/main** (Dev Local BUILD SUCCEEDED + App Store
BUILD SUCCEEDED earlier this session):
- Pluggable `ClientTransport` seam in `fichero/fichero-api-client/Sources/FicheroAPIClient/FicheroClient.swift`:
  `TransportMode` = `.https` / `.uds(path:)` / `#if os(macOS) .inMemory`.
- UDS (Mac local), HTTPS (iOS/remote/sharing/debug), in-memory/PythonKit (Mac Dev/DMG experiment, all
  `#if os(macOS)` in `.../FicheroAPIClient/InMemory/`).
- Auth: loopback-owner marker `scope["fichero.transport"] in ("uds","inmemory")` → owner
  (`fichero-engine/src/fichero/api/auth.py:471`); `AuthTokenMiddleware` recognizes `http+unix` → bootstrap token.
- Media (`fichero-res://`), reader, thumbnails, workflows, activity all route through the transport via
  `StorageResourceLoader` → generated OpenAPI client (`fichero/fichero/Services/StorageResource/`).
- #18 startup: `EmbeddedBackendService` auto-restarts a crashed embedded engine (crash-loop guard:
  5 restarts / 60s → `.failed`). Full-window BackendConnectionView → toolbar-status is the S1 design
  (see `2026-07-20-startup-transport-ux-fabel-review.md`), NOT yet implemented.
- `library_discovery.py` DELETED (dead home-crawl); recents-registry is the list source.
- #4039 FIXED: `fichero-engine/tests/unit/conftest.py` attaches auth middleware at conftest LOAD →
  verify-all reliable again (~8056 pass). Run the suite ALONE, `--ignore=tests/perf` (a perf test hangs
  in db_embeddings), `--timeout=75 --timeout-method=thread`, `FICHERO_MULTIUSER=0`,
  `PYTHONPATH=<worktree>/fichero-engine/src`, engine venv `/Users/danieltubb/code/fichero/.venv`.

## KNOWN OPEN: FicheroClient "Cannot find InMemoryASGIClientTransport in scope" (Xcode)
The code is CORRECT — `.inMemory` (FicheroClient.swift ~L221) is `#if os(macOS)`-guarded and the InMemory
files start with `#if os(macOS)`. Daniel's Xcode error is STALE SPM state (PythonKit — the macOS-only dep
those files import — not resolved). Fix in flight: synced `~/code/fichero` to origin/main +
`xcodebuild -resolvePackageDependencies` (log: `$CLAUDE_JOB_DIR/tmp/resolve_pkgs.txt`). Verify a Dev Local
build compiles; if it does, tell Daniel to just let packages resolve / clean build. Only a real code fix
if the Dev Local build actually fails.

## Decisions Daniel APPROVED 2026-07-21 (recorded as issue comments)
- **#2577** internal/external split = Option A: promote only the EXTERNAL HTTPS-client surface of cli/mcp
  to top-level; internal/embedded stays in `fichero-engine` (grouped by #2566). Unblocks #2576, #2562.
- **#2594** leave `runner.py` under `api/routes/workflow_execution/` (moving it regresses the swiftui
  contract walker); core consolidation already landed → closeable.
- **#3740** (a) YES auto-wire existing inverses (crop/uncrop, split/unsplit, group/ungroup,
  batch-apply/undo); (b) content-representation revision = non-invertible if downstream state can advance;
  (c) keep authority-refresh / library-columns / locations-resolve EXCLUDED via precise rules; (d)
  sandbox/security-scoped-access = ephemeral → excluded.
- **#3759** registry/open = engine-only; storage/debug/{doc_id} = engine-only (exposes paths); 
  workflow-execution/stream/{thread_id} = Swift-wired. Nothing retired.
- **#2561** agent identity = Option A co-author convention (already de-facto) → closeable with documented policy.
- **#3752** `folder`→`collection` naming confirmed; TIMING = its own gated batch AFTER App Store/TestFlight
  builds ship (highest blast radius; needs idempotent ALTER+backfill migration). Do NOT do now.

## Engine hygiene reorg — plan + method
Plan: `docs/design/engine-package-reorg.md`. Method = the proven identity-preserving shim
(`from fichero.X import *; import sys; sys.modules[__name__] = sys.modules["fichero.X"]`; see
`fichero-engine/src/fichero/importers/iiif_import.py:1`). Ordered sequence: mcp → media → core → security →
llm → db → models. God-nodes (models.py 505 sites, db.py 337, llm.py 311, knowledge_models 291) STAGED
with sys.modules shims. models/ = single package (relocate knowledge_models/hermeneutics_models in); 
migrations → `db/migrations/` dir; pykeen_inference + graph_reasoning → `kg/`; spatial_models = canvas_models.

**DONE:** `mcp/` (commit 3e7c27adb+205e34d2f on main; route count 360→360, imports OK, grep clean of
`fichero.mcp_*`, guardrails 0) — retroactive full-suite gate was running at handoff
(`$CLAUDE_JOB_DIR/tmp/gate_mcp.txt`; 0 poison errors — CONFIRM it shows "N passed" before trusting it).

**NEXT reorg step:** `security/` (next domain). Then importers/ (may already be partly done — check),
then the god-nodes (staged), then #2569 routes grouping (157 import sites — mechanical, shim playbook, but
sequenced AFTER the store builds ship), then #2594 execution follow-up (leave runner), then #3740 Pile 1.

## Autonomous-now queue (no decision needed)
1. Confirm mcp gate green (`gate_mcp.txt`).
2. Confirm the FicheroClient Dev Local build compiles (stale-SPM verification above).
3. #2562 — verify CLI round-trips over loopback HTTPS; fix if broken (fully independent).
4. #3740 Pile 1 — register the already-existing image/group inverses through `registry.invoke` + tests.
5. security/ reorg (gated full suite + 3 guardrails + route count, then push + ff-pull ~/code/fichero).
6. Then #19 login (Settings, not a wall — see startup-transport-ux review).

## HARD gotchas (learned this session)
- **Lane collisions / git-state tangles:** a concurrent process landed the mcp move inside my `docs(design)`
  commit (3e7c27adb) authored "Daniel". ALWAYS `git show --stat` a commit before trusting its provenance;
  NEVER two workers on overlapping files; author reconciles collisions.
- **Package.resolved churn** breaks `git rebase` after in-memory/SPM merges — revert Package.resolved,
  push WITHOUT rebase (you're the sole pusher).
- **Serialize heavy jobs.** Over-parallelization (17 procs) wedged the machine. One xcodebuild / one full
  pytest at a time.
- **Gate BEFORE push** — Daniel's explicit standing instruction this session ("do verify, build gate, etc
  before you run"). The mcp move breached this (pushed then gated); don't repeat.
- **Stray beta engine on :8765** causes ~15 spurious integration failures — env, not code.
- **Batch worktree** = `/Users/danieltubb/code/fichero-worktrees/batch` (currently == origin/main).
  Integration merges happen in `~/code/fichero-worktrees/integrate`, NEVER `~/code/fichero`.
- A 15-min ScheduleWakeup loop is/was armed to keep momentum.
