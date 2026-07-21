# Engine startup speedup plan (#4038)

Status: measurement + plan only. No engine code changed — a reorg (security/mcp/
importers/db/llm/models/kg package split) is churning module structure in
parallel; implementation should land **after** that reorg merges.

## 1. Reconciling the two numbers on record

Two conflicting figures were on record:
- Stale: "10.9s cold import = 64% of a ~17s startup, lever = lazy tool imports."
- Newer: S3 of the startup fabel review — "cold import is 2.11s, not 10.9s;
  lazy-import work already landed."

**Re-measured now (2026-07-21), on this worktree, engine venv
`/Users/danieltubb/code/fichero/.venv/bin/python` (3.12.13):**

```
bare interpreter (python -c "pass")........ 0.03s
import fastapi alone........................ 0.45s
import fichero.api.main, .pyc absent (cold). 4.30s  (one-time bytecode compile)
import fichero.api.main, .pyc present (warm) 2.77s  → 2.47s on repeat runs
```

**The newer number is correct and still holds: warm cold-start is ~2.1–2.5s**,
matching the S3 figure. The 10.9s figure is stale/superseded — do not use it.
`python -X importtime` shows **zero** `torch` / `pykeen` / `mlx*` /
`transformers` / `sentence_transformers` frames anywhere in the import graph
(`fichero.pykeen_inference`, `fichero.mlx_runtime`, `fichero.mlx_model_store`
are already thin lazy wrappers, 1–3ms self each) — confirming the earlier
lazy-import work already landed and those heavy ML libraries are not the
remaining cost.

Reproduce: `PYTHONPATH=<worktree>/fichero-engine/src /Users/danieltubb/code/fichero/.venv/bin/python -X importtime -c "import fichero.api.main" 2> /tmp/importtime.log`

## 2. Where the ~1.82s of `import fichero.api.main` cumulative time actually goes

Aggregated from the `-X importtime` log (self-time, i.e. the module's own
top-level exec cost, not children — children are counted separately):

| Group | Self-time (ms) | Share | Notes |
|---|---:|---:|---|
| **`fichero.api.routes.*` (94 modules)** | **801** | **44%** | One monolithic `from fichero.api.routes import (...)` block, main.py:1286–1370. Imported **unconditionally**, before any feature-tier check. |
| fastapi + fastapi.applications/.routing/.params/.openapi.models + pydantic + pydantic_core | ~400 | 22% | Framework baseline. `import fastapi` alone costs 450ms wall. |
| `fichero.models` + `fichero.knowledge_models`/`knowledge.knowledge_models` | ~80 | 4% | Domain Pydantic model modules, imported by nearly every route module. |
| `apscheduler.*` (21 submodules) | 62 | 3% | Pulled in by `fichero/workflows/scheduler.py` and `fichero/workflows/tasks.py`, which are imported at module-load time by `api/routes/schedules.py` and `api/routes/tasks.py`. |
| `langchain_core` | ~3 (self) | <1% | Cumulative 107ms shown in the raw log is misleading — it's `langchain_core` pulling in the *shared* pydantic/importlib.metadata machinery that fastapi/pydantic also pay for, not langchain's own cost. Self-time is trivial; **not** a real lever despite the #4038 issue text calling out "~87ms". |
| everything else (asyncio, site, importlib.metadata, stdlib) | remainder | ~26% | Interpreter/stdlib baseline, not fichero's to cut. |

Top individual offenders by self-time (ms): `claim_curation` 73,
`apscheduler.schedulers.base` 54, `fichero.knowledge.knowledge_models` 43,
`fastapi.openapi.models` 43, `fichero.models` 37, `fichero.orchestration_policy`
32, `fichero.api.routes.documents` 30, `.workflows` 25, `.entities` 25,
`.search` 23, `.hermeneutics` 21, `.image_editing` 21, `.claim_links` 20,
`.claims` 18, `.activity`/`.model_comparison`/`.research_crud`/`.chat` 14–17
each. No single route module dominates — the cost is the **sum of ~90 small
Pydantic-model-heavy modules**, not one big culprit.

## 3. What's genuinely boot-required vs deferrable

**Cannot defer** (needed for FastAPI app construction / OpenAPI contract):
- `fastapi` + `pydantic`/`pydantic_core` import (~400ms) — the ASGI app object
  and its exception handlers must exist before uvicorn can serve anything.
- The **core** route set already carved out in `main.py` — `activity`,
  `authz`, `auth_accounts`, `pairing`, `sandbox_access`, `changes` (the SSE
  reactive spine the SwiftUI stores subscribe to unconditionally) — these must
  be registered before first response.

**Already lazy** (confirmed by the import graph, nothing to do):
- `torch`, `pykeen`, `mlx_runtime`/`mlx_model_store`, `transformers`,
  `sentence_transformers` — all deferred inside their call sites already.
- `langchain_core`/`langgraph` proper (self-cost is negligible; don't touch).

**Deferrable, concrete targets:**

1. **`apscheduler` (~60–85ms).** `fichero/workflows/scheduler.py` (lines
   23–29) and `fichero/workflows/tasks.py` (lines 20–22) import
   `AsyncIOScheduler`, `CronTrigger`/`IntervalTrigger`/`DateTrigger`,
   `MemoryJobStore`, `AsyncIOExecutor` at module top level. These are only
   needed when a `WorkflowScheduler` instance is actually constructed
   (schedule created/started), not merely when the `schedules`/`tasks` route
   modules are imported for their Pydantic request/response types. Move the
   `apscheduler.*` imports into the `WorkflowScheduler.__init__`/`start()`
   methods (and the equivalent constructor in `tasks.py`); keep the
   dataclass/pydantic types (`Schedule`, `ScheduleConfig`, `ScheduleType`,
   `ScheduleStatus`, `ScheduleRun`) importable without pulling apscheduler.
   **Risk: low** — isolated to two files, no cross-module callers touch
   apscheduler directly (confirmed via grep — the only two importers are
   `scheduler.py` and `tasks.py`).

2. **The `fichero.api.routes.*` monolithic import block (801ms, 44% of
   total) — the real lever, but it needs a structural fix, not a per-module
   patch.** `main.py` already has a two-tier design for *registration*
   (`_CORE_ROUTE_SPECS` + `register_tiered_routes(feature_tier)` filters
   which routers get `app.include_router()`'d based on
   `FICHERO_FEATURE_TIER`), but the **import** of all 94 route modules at
   line 1286 happens unconditionally, before any tier check runs — so a
   `release`-tier engine pays the same import cost as `dev` tier today.
   Fixing this means importing route modules lazily inside
   `get_route_specs_for_tier()` (or splitting the big import into
   per-route-module imports done just-in-time as each tier's spec list is
   built) instead of one static `from fichero.api.routes import (...)` block.
   **Caveat found while measuring:** a 2026-05-28 comment in `main.py`
   ("ship ALL gated features so they're reviewable in release builds") means
   `release` tier today enables almost the same route set as `dev` — so this
   change buys close to zero at the *current* tier configuration. It only
   pays off if/when tiers are re-diverged (e.g. a slim `release` tier that
   really does exclude `dev`-only routes like `kg_sparql`, `kg_curation_rules`,
   `search_explain`, `iiif`, `triggers`). **Do this refactor for correctness
   and future headroom, but do not expect it to move the needle until the
   tier policy also changes** — flag both to Daniel together, don't ship one
   without the other.

3. **Nothing else stood out.** Every route module's own top-level imports are
   `fastapi`, `pydantic`, and fichero's own `models`/`knowledge_models`/`db`
   modules — no route module pulls in an unexpectedly heavy third-party
   library at module scope (checked `mcp_tools.py`, `research_tools.py`,
   `kg_pykeen.py`, `research_agents.py` directly). The #4038 issue text's
   "2 eager tool modules" and "langchain_core ~87ms" both turned out, on
   re-measurement, to be smaller/already-lazy than believed — see §2.

## 4. Staged plan, ordered by ROI

| Stage | Change | Expected savings | Risk | Files |
|---|---|---:|---|---|
| **1** | Lazy-import `apscheduler.*` inside `WorkflowScheduler`/task-scheduler constructors instead of module top level | ~60–85ms | Low — 2 files, no other callers | `fichero/workflows/scheduler.py`, `fichero/workflows/tasks.py` |
| **2** | Re-diverge `release` vs `dev` feature tiers so `release` genuinely excludes dev-only route modules (product decision, not just code) | 0ms until paired with Stage 3 | Medium — needs Daniel's sign-off on which routes are dev-only again | `fichero/api/main.py` `_CORE_ROUTE_SPECS` tier flags |
| **3** | Make route-module import itself tier-aware (import only the modules whose spec is enabled for the resolved tier, inside `get_route_specs_for_tier`/`register_tiered_routes`, not via the static top-of-file `from fichero.api.routes import (...)`) | Proportional to modules excluded by Stage 2 — e.g. excluding ~15 dev-only modules (`kg_sparql`, `kg_curation_rules`, `kg_claim_analysis`, `search_explain`, `iiif`, `triggers`, `multilingual`, `citation_usages`, `canvas`, `local_models`, `mcp_servers`, `orchestration`, ...) would save roughly 100–150ms at `release` tier, based on their measured per-module self-times | Medium — must preserve OpenAPI contract stability for the enabled tier; contract tests (`fichero-engine/tests/contracts/openapi.json`) must still pass for whichever tier CI runs | `fichero/api/main.py` |
| **4** | Re-measure the **actual current bottleneck**: spawn → uvicorn-ready → connect → readiness chain (S3's own conclusion — import is no longer the dominant cost once UDS (S2) drops the TLS handshake). `py-spy`/`cProfile` the real spawn path, not just `-X importtime` | Unknown until profiled — likely bigger than the ~150–250ms available from Stages 1–3 combined | N/A (measurement stage) | spawn/bind path, not import path |

**Total expected savings from Stages 1–3 alone: roughly 150–250ms off a
~2.1–2.5s warm cold-start** (apscheduler ~70ms + tiered-import ~100–150ms,
contingent on Stage 2's product decision). That is a real but modest win —
**it does not change the conclusion already reached in the fabel review: the
import path is not where the remaining startup latency lives.** Stage 4 (the
spawn→ready→connect chain, and UDS removing the TLS handshake) is where S3
already pointed and remains the higher-ROI target; this plan's Stages 1–3 are
a cheap, low-risk cleanup to do alongside it, not a substitute for it.

## 5. Interaction with the ongoing reorg

Implementation lands after the security/mcp/importers/db/llm/models/kg package
split merges. Boundary notes for whoever picks this up:
- `fichero/workflows/scheduler.py` and `tasks.py` (Stage 1) are workflow/
  execution-domain files — confirm their post-reorg home (likely stays under
  a `workflows/` or folds into `execution/`) before patching; don't patch on
  a branch that's about to move the file.
- `fichero/api/main.py`'s route-import block and tier machinery (Stages 2–3)
  live in `api/` and are reorg-adjacent only insofar as route modules import
  from the packages being split (`db/`, `models/`, `kg/`, `mcp/`) — those
  imports are by name, so as long as the reorg preserves import paths (or
  the reorg's own plan documents the new paths), Stage 3's lazy-import
  refactor is a mechanical follow-up, not a redesign. Coordinate with
  whichever lane owns `api/main.py` last (per house rules: "Lane E
  (transport/bind) and Lane P (imports) both touch main.py — keep edits
  disjoint or serialize").
- No `mcp/`, `security/`, `importers/`, `db/`, `llm/` internals need to
  change for this plan — the lazy-import boundary is entirely within
  `api/main.py` + `workflows/scheduler.py` + `workflows/tasks.py`.

## 6. Re-verification command

```
PYTHONPATH=<worktree>/fichero-engine/src /Users/danieltubb/code/fichero/.venv/bin/python -X importtime -c "import fichero.api.main" 2>&1 | tail -1
```
(reports the cumulative import time for `fichero.api.main`; compare the
cumulative-µs figure before/after each stage, and re-run
`time python -c "import fichero.api.main"` three times warm to sanity-check
wall-clock.)
