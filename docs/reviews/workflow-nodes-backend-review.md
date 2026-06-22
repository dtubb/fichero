# Workflow / Nodes — Backend: What's Needed (Review)

_2026-06-22 · branch 0.0.2 · Opus read-only review (PONYTAIL lens) + lead audit. Read-only; nothing changed by this review._

## TL;DR — is it well-engineered enough to build on?
**Yes, the bones are good** (one tool registry, one save contract now fail-loud, typed NodeDef/EdgeDef, single DB write path after #2508/#2514, execution off the main loop). **But two structural debts will compound** as image-editing / entity-cleanup / SVO / ontology chains get stacked on top — fix these first:

1. **P0 — the diagram lies.** The workflow **preview/diagram builds a *parallel* graph** (`enable_parallel=True`) but the **actual run path is hard-disabled to sequential** (`runner.py:654 enable_parallel=False`). So the Mermaid you see ≠ the graph that runs, and ~480 lines of fan-out machinery are built-but-unverified on the run path. → **#2532**. Decide: finish the checkpointer test + flip it on, or delete the fan-out path. Don't keep both.
2. **P1 — typing stops at the door.** Running `State` and persisted `Workflow.nodes/edges` are `dict[str,Any]`; the typed `NodeDef`/`EdgeDef` boundary is cosmetic at runtime (the #2523 unwired-`documents`-port bug lives in this gap). Fix at the **persistence boundary** (type `Workflow.nodes/edges`), NOT the running State. → #2524 spine.

## Filed issues (the actionable decomposition)
- **#2532** (P0) — resolve the enable_parallel fork (preview graph ≠ run graph).
- **#2533** (P1) — collapse per-family `save_artifact` wrappers onto `llm_base.save_artifact` (drift surface for the parent-reroute bug).
- **#2534** (P2 bundle) — EdgeDef condition/route_key validator; surface save-returns-None as a run error; cap the running-workflows registry; document State-stays-TypedDict.
- **#2524** (EPIC) — node-editor + typed-contract review: type `Workflow.nodes/edges` end-to-end, kill source_port/source_port_id drift, clickable/editable edges, visible + user-chosen fan-out, native diagram.
- **#2525** — viz PNG / Pyppeteer (drop server mermaid PNG; native editor is source of truth).

## Lead frontend/contract audit (companion to the backend review)
- Palette is **registry-driven** (good) but has **hardcoded duplications**: per-tool icon/color maps (`WorkflowNodeRow/Card`), a hardcoded **port-compat map** `"file":["files"]` (`WorkflowCanvasView+EdgeConnection.swift:16` — same blind spot that hid the HTR documents-port), vision-tool name lists.
- **~236 hand-rolled URL/HTTP sites** across Swift services bypass the generated OpenAPI client (should be swept like the auth sweep).
- Backend **pydantic is partial**: response_models at some endpoints, but workflow state + persisted nodes/edges are `dict[str,Any]`.

---

## Full Opus backend review

# Fichero Workflow Backend — Architecture Review (Opus / PONYTAIL lens)

Read-only. Scope: execution core, tool system, composability, typed-contract fix. Evidence cited `file:line`.

## VERDICT
**Sound enough to build on — the bones are good (typed defs, single registry, single save contract, single DB write path). But two structural debts will compound under the transcription/HTR/SVO load: (1) the graph-level parallel fan-out is fully built yet hard-disabled in the only real run path, so "scale" today is sequential; (2) the running state is `dict[str,Any]` end-to-end (`State` TypedDict + persisted `Workflow.nodes/edges`), so the typed `NodeDef`/`EdgeDef` boundary is cosmetic at runtime.** Fix those two before piling six tool families on top; everything else is incremental.

## KEEP (solid)
- **One registry, ports not persisted.** `register_tool` decorator + `TOOLS`/`TOOL_DEFS` dicts (`registry.py:31-119`); `enrich_node_with_ports` rehydrates ports from the registry at load (`registry.py:180`), `model_dump_for_storage` strips them (`types.py:397`). Single source of truth for port shape — good, copyable.
- **One save contract, now fail-loud.** `llm_base.save_artifact` (`llm_base.py:429-578`) is the canonical per-page/parent resolver and the #2430/#2523 hardening landed *here*: no file_path fallback when an explicit id is given, fail-loud + `return None` rather than reroute to the parent PDF, `document=` passthrough to dodge the cross-thread re-fetch race. This is the right place for it.
- **Typed graph vocabulary.** `NodeDef`/`EdgeDef`/`ToolDef`/`PortDef`/`OutputSchema` are real Pydantic models with docstrings (`types.py:279-597`).
- **Parallel-merge reducers are correct in principle.** `Annotated[..., _merge_*]` reducers on `State` (`types.py:23-122`, used at `types.py:240-271`) are the right LangGraph pattern for concurrent-branch state merges.
- **Execution off the main loop.** Workflows run on a worker thread with a thread-safe `queue.Queue` for SSE (`runner.py:34-36`, #1000).

## FRAGILITIES / RISKS

### P0 — The parallel fan-out is dead in the only real path
- **`runner.py:654` hard-codes `enable_parallel=False`** in `_run_workflow_in_background` — the actual user run. Comment (runner.py:648-653): deferred "until the dynamic fan-out path has a checkpointer-backed regression test."
- Meanwhile `build_graph(enable_parallel=True)` is the default (`builder.py:313`) and is used by *previews, diagrams, batch, model_comparison* (`visualization.py:80,133`, `threads.py:683`, `batch.py:524`, `runner.py:505` preview). **So the Mermaid the user sees and the graph that actually runs are different graphs.**
- ~480 lines of fan-out machinery (`_make_fan_out_function` 962, `_make_route_map_fan_out_function` 1037, `_make_parallel_node_function` 1125, `_make_aggregation_function` 1440, all the `Send`-API reducers) are **built but never exercised in production**. It is not dead code (preview/batch hit it) but it is *unverified on the run path*.
- **Consequence at scale:** cross-file graph parallelism is OFF. A 500-page PDF / large folder processes files sequentially through the node; the only concurrency is intra-tool (`VISION_FAN_OUT_CONCURRENCY=4` semaphore, `builder.py:43`). Two divergent code paths (sequential prod vs parallel preview/batch) will drift — bugs fixed in one won't be in the other. **This is a bigger risk than any cosmetic item.** Decide: either finish the checkpointer regression test and flip it on, or delete the fan-out path and commit to sequential + intra-tool concurrency. Do not leave both half-alive.

### P1 — `State` is `dict[str,Any]`; typed NodeDef/EdgeDef stops at the door
- `State(TypedDict)` (`types.py:221-271`): `inputs`, `outputs`, `parallel_results`, `parallel_document` are all `dict[str,Any]`/`Any`. The runtime carries untyped blobs; the Pydantic typing on `NodeDef`/`EdgeDef` is for the *definition*, not the *execution state*.
- Combined with persisted `Workflow.nodes/edges` being `dict[str,Any]` (established in #2524 frontend audit), there is **no typed contract on the wire or in the running state** — only at the API-serialization edge. Consequence: port/output-key mismatches surface as runtime `KeyError`/`None`, not validation errors; the #2523 "un-wired documents port" class is exactly this.

### P1 — Save contract is re-wrapped per family (drift surface)
- `save_artifact` is canonical in `llm_base.py:429`, but **re-wrapped in every media family**: `vision_base.py:1259`, `audio_base.py:358`, `video_base.py:323` — each "Wraps llm_base.save_artifact with file_path-based document lookup." Plus scattered call sites (`vision_base.py:1579,1626,1996,2013`; `extract.py:280`; `clean_text.py:273`; `translate.py:123`; `language_identification.py:173`).
- The #2430/#2523 fix lives in `llm_base`, so the wrappers *currently* inherit it — but each wrapper re-derives document lookup, so the **per-page-vs-parent contract is enforced in one place but invoked through N family-specific shims**. The next family added (image editing, SVO, ontology, catalogue) will copy a wrapper and can silently reintroduce the parent-reroute bug. Not enforced by a shared type or test — by convention.
- `vision_base.py:2011` logs `"save_artifact returned None"` and continues — a soft swallow at the call site (the None is by-design fail-loud upstream, but the caller treats a genuine miss as a warning, not an error surfaced to the run).

### P2 — `NodeDef` null-coercion validators paper over Swift serialization
- Three `convert_none_to_empty_*` validators (`types.py:366-395`) exist solely because Swift's OpenAPI client serializes omitted optionals as JSON `null` (docstring cites #780). This is the untyped-wire tax. Harmless now, but it means "set tool" saves arrive with `provider_name=null` and rely on coercion — fragile, and a symptom of the dict-typed persistence.

### P2 — `condition` vs `route_key`/`route_map` mutual-exclusion is docstring-only
- `EdgeDef` (`types.py:410-452`): docstring says route_key is "mutually exclusive with condition" but **no validator enforces it**. A malformed edge with both set has undefined precedence in `build_graph`.

### P2 — Unbounded in-memory run registry
- `_running_workflows: dict[str,dict]` (`runner.py:36`) — no cap visible. Many concurrent workflows (the stated future) → unbounded worker threads + state dicts. Fine for single-user-now, a real limit at "many concurrent."

### P2 — Broad `except Exception` in save_artifact
- `llm_base.py` save: outer `except Exception: return artifact_id` (may be None). Logs `.error` but the run continues; combined with the call-site warning-not-error, a systematic save failure degrades to "warnings in the log, empty artifacts." The `SystemicErrorDetected` rate-detector (`builder.py:244`) catches tool *exceptions* but not save-returns-None.

## PONYTAIL REWORK (smallest change, most soundness)
1. **Resolve the parallel fork (P0).** Cheapest sound move: write the one checkpointer-backed regression test the comment asks for, flip `runner.py:654` to `enable_parallel=True`, delete nothing. If that test is weeks out, instead **delete the fan-out path** (`_make_fan_out_function`, `_make_route_map_fan_out_function`, `_make_parallel_node_function`, `_make_aggregation_function`, the parallel-only reducers) and make previews build the same sequential graph — one path, less code. Either is fine; *having both is the bug.* Recommend finishing the test (the machinery is real value for HTR fan-out).
2. **Make `save_artifact` the only entry (P1).** Delete the three per-family wrappers; have vision/audio/video call `llm_base.save_artifact` directly with `document=`. One contract, one call shape, no copy-drift. ~3 small edits, removes ~40 lines.
3. **Add the one missing validator (P2).** `@model_validator` on `EdgeDef` rejecting `condition` + `route_key` both set. 5 lines, kills an undefined-behavior class.
4. **Don't over-build typed State.** Do NOT introduce a Pydantic runtime-state model — LangGraph wants a TypedDict and the reducers need it. The typed win is at the *persistence boundary* (see below), not the running state. Leave `State` as-is.

## TYPED-CONTRACT FIX (Workflow.nodes/edges → list[NodeDef]/list[EdgeDef])
- **Right way:** change the persisted `Workflow` model fields from `dict[str,Any]` to `list[NodeDef]`/`list[EdgeDef]` (the models already exist and are already in OpenAPI), serialize via `model_dump_for_storage()` (already strips ports), then regen OpenAPI + Swift client. This collapses the `to_workflow_def` conversion and kills the source_port/source_port_id drift at the source.
- **Blast radius (verify before touching — these are god-ish):** `Workflow` model in `models.py`; `to_workflow_def` (`runtime.py`) conversion; every workflow CRUD route; `model_dump_for_storage`; DuckDB column type (JSON blob → still JSON, but typed on the Python side); OpenAPI regen (`sync_openapi_schema.sh`) → Swift `Components.Schemas.Workflow` → the ~236 hand-rolled URL sites that build workflow bodies. **Per rule #9-retired: this touches a persisted real DB → needs an idempotent migration** for existing stored workflows (old dict shape → validated NodeDef/EdgeDef on read). Do it as: add tolerant `field_validator(mode="before")` on the new typed fields that accepts the legacy dict, so old rows load; no destructive migration needed.
- Sequence: (1) flip parallel fork first (P0, isolated), (2) typed-contract fix (this), (3) collapse save wrappers (P1) — independent, can parallelize.

## TOP ISSUES TO FILE
1. **Resolve enable_parallel fork** — finish checkpointer regression test + flip `runner.py:654` to True, or delete the fan-out path; stop shipping two divergent graphs. **P0.**
2. **Type Workflow.nodes/edges end-to-end** — `list[NodeDef]`/`list[EdgeDef]` + tolerant before-validator for legacy rows + OpenAPI regen. **P1.**
3. **Collapse per-family save_artifact wrappers** onto `llm_base.save_artifact` (delete vision/audio/video shims). **P1.**
4. **EdgeDef validator: reject condition + route_key both set.** **P2.**
5. **Surface save-returns-None as a run error**, not a per-call-site warning (feed into `SystemicErrorDetected`). **P2.**
6. **Cap `_running_workflows`** / bound concurrent worker threads before "many concurrent workflows." **P2.**
7. **Decide on `State` typing posture** — document that running state stays TypedDict-by-design (so future workers don't "fix" it into Pydantic and break reducers). **P2 / doc.**
8. **Port-vocabulary canonicalization** (source_port vs source_port_id) — fold into issue #2 so it's done once at the typed boundary. **P2.**
