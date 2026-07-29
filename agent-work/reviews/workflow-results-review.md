# Workflows & Results-Surfacing Review — 2026-07-29

Design + fragility review of the whole "workflows and how results reach the user"
surface: server pipeline (run → step outputs → artifacts → activity), the SwiftUI
surfaces (node editor, activity monitor, artifact panel, content pane), default
workflows, model presets, comparison, and testing/health visibility.

All claims below are grounded in code read on `integration` (post-#4227 rename).
Paths: `fs/` = `fichero-server/src/fichero_server/`, `app/` = `fichero/fichero/`.
Companion file: `workflow-issue-drafts.md` (ready-to-file drafts).

---

## 0. Executive summary

The core promise — *a non-technical user can see what the system is doing and where
its results went* — fails today for structural reasons, not polish reasons:

1. **The provenance chain is severed at the source.** `Artifact` has `run_id` and
   `step_name` fields (`fs/models/__init__.py:589,592`), but the live execution path
   never populates them: `_save_artifact_sync` writes `run_id=task_id`
   (`fs/workflows/tools/llm_base.py:600`) and `task_id` is never placed into state on
   the live `/execute` path (`fs/workflows/runtime.py:144-163`,
   `fs/execution/runner.py:902-907`) — only the scheduler/file-watcher path sets it,
   to a UUID unrelated to any thread id (`fs/workflows/builder.py:1879`). Consequence:
   `GET /threads/{id}/run`'s `run_artifacts` is structurally always empty
   (`fs/api/routes/workflow_execution/threads.py:236-242`), the app never renders
   `runId` anywhere in `Views/`, and no artifact can be traced to the run or step
   that made it.
2. **Results reach the content pane only for transcribe-family tools, and the pane
   doesn't refresh even then.** Promotion into `Document.page_content` is per-tool
   opt-in (`update_page_content=True` only on transcribe/handwriting/audio —
   `fs/workflows/tools/*.py`), the server emits `document.updated` only at successful
   run completion (`fs/workflows/completion.py:184`), and on the client the fresh
   value lands in `childrenCache` while both content-pane accessors read only
   `currentDocuments` (`app/Views/Inspector/Source/DocumentInspectorContentV2.swift:33-35,325-327`;
   `app/Views/Shell/ContentView/ContentView+StatePreview.swift:135-157`). The one
   correct refresh path (`refreshDocumentsByIds` →
   `app/Models/DocumentStore+Helpers.swift:66-84`) is neutralized by the accessor.
3. **Pause is a dead-end state; cancel is advisory with unbounded latency.** Both are
   plain dict flags checked once per LangGraph event tick
   (`fs/execution/runner.py:937-1035`); a paused run cannot be cancelled, cannot be
   deleted (`DELETE` 409s — `threads.py:601-608`), is never recovered by
   `recover_stale_runs` (only `running` is — `fs/workflows/activity_store.py:483`),
   and resume 404s without a checkpoint (`core.py:446-450`). Cancelled/failed runs
   never call `complete_run_documents`, leaving documents at `Status.processing`
   forever (`fs/execution/runner.py:1314-1333` is success-only).
4. **The node editor's semantics are invisible in the shipping build.** Node kind,
   port type and data type are all untyped strings; per-port geometry and data-type
   icons are behind a dev-tier flag, so parallel edges collapse onto one point and
   render as a single line (`app/Views/Workflow/Canvas/WorkflowCanvasView+EdgeConnection.swift:228-233`);
   fan-out badges come from hardcoded tool allowlists that omit `zoom` — the actual
   1→N step — and decorate the wrong edge
   (`app/Views/Workflow/Canvas/WorkflowEdgeView+Helpers.swift:32-58`).
5. **16 palette-visible tools cannot execute** (`if`, `switch`, `loop`, `filter`,
   `merge`, all five export nodes, `custom_llm`, …): declared in
   `fs/workflows/registry_builtins.py` with no `@register_tool` implementation,
   served unfiltered by `GET /api/workflows/tools`
   (`fs/api/routes/workflow/workflows.py:365-372`), and fatal at graph build
   (`fs/workflows/builder.py:472-474`).

The **good news** is that most of the persistence needed for a "what actually
happened" run-trace view already exists (checkpoints, `progress_timeline`,
`workflow_snapshot`, Mermaid diagrams) — it is being destroyed or left unlinked at
three specific points (§3.3), all fixable without new architecture.

---

## 1. As-built architecture

### 1.1 Server: three execution paths (and one dead one)

| Path | Entry | `workflow_runs` row | SSE | state `task_id` |
|---|---|---|---|---|
| Live run (the app's) | `POST /api/workflow-execution/execute` → `fs/execution/runner.py:559` | yes | yes | **never set** |
| Batch | `fs/execution/batch.py:561` | **no** | own queue | never set |
| Scheduler / file-watcher | `fs/workflows/builder.py:1858` | no | no | random UUID |
| `fs/workflows/executor.py` (806 lines) + `state.py` (497 lines) | — | — | — | **dead code**, test-only importers |

The live path runs LangGraph `astream_events(v2)` on a dedicated daemon thread per
run (`fs/api/routes/workflow_execution/core.py:355-370`), with a per-run
`WorkflowEventHub` (private queues + 2000-event replay — `fs/execution/runner.py:107-161`).

Persistence per step is split across three stores:
- **LangGraph checkpoints** (`fs/workflows/checkpointer.py:147,161`) — the only
  per-step state, deliberately compacted: `compact_output_for_state`
  (`fs/workflows/types.py:27-47`) deletes `texts`/`results`/`values` and keeps counts.
- **`workflow_runs`** (`fs/workflows/activity_store.py:41-56`) — status, log,
  `workflow_snapshot`, `node_name_map`, `progress_timeline`, `diagram_mermaid`.
- **`progress_timeline`** — per-node and per-file steps with timings/status
  (`fs/execution/runner.py:1058-1065`, `783-828`) — but flushed **only at terminal
  transitions** (`runner.py:1381,1435,1489`, pause `:1000`, cancel `:1024`); a crash
  loses it entirely.

### 1.2 Result promotion

There is no run-level "result". Per step, `_save_artifact_sync`
(`fs/workflows/tools/llm_base.py:534-676`) writes an `Artifact` and, iff the tool's
`LLMToolConfig.update_page_content` is true and the user hasn't hand-edited
(`page_content_user_edited_at` guard, `llm_base.py:615-627`, #672), overwrites
`Document.page_content` and sets `Status.processing`. At successful completion,
`complete_run_documents` (`fs/workflows/completion.py:98`) flips docs to `completed`,
appends a provenance entry to `doc.workflow_runs` (`:137-142` — the ONLY doc→run
link), and emits `document.updated` (`:176-196`).

`update_page_content=True` tools: `transcribe`, `transcribe_review`, `handwriting`,
`audio_transcribe`. Everything else — describe, analyze, catalogue, clean_text,
translate, extract — is artifact-only by design. So for most workflows the "final
result" is *definitionally* buried in the artifacts tab; there is no notion of
promoting a run's terminal-node output anywhere.

### 1.3 App: how results and activity are consumed

- **Change stream substrate** is sound: `ObservableDomainStore` + debounced granular
  splice (`app/Models/DocumentStore+ChangeStream.swift:30-51`), own-write echo
  suppression, batch splice (#4235). But splice targets `collections` /
  `currentDocuments` / `childrenCache` — and never `selectedDocument` or the shell's
  `@State detailDocument` / `pageFocusDocument` snapshots
  (`app/Views/Shell/ContentView/ContentView.swift:84,99`).
- **Reader pane** (`app/Views/Reader/Page/PageContentPane.swift:7,28-39`) renders a
  passed-in `Document` value with no refresh hook at all beyond its parameter.
- **Inspector pane** re-resolves against `currentDocuments` only
  (`DocumentInspectorContentV2.swift:33-35`), and its refresh trigger is gated on
  *this process's* SSE counters (`executionObserver.fileCompletedCount`,
  `DocumentInspectorContentV2.swift:73-80`) — CLI/MCP/other-window runs never fire it.
- **Two parallel live-run stores**: `WorkflowExecutionObserver` (window-scoped,
  fed by whoever launched the run) and `WorkflowExecutionStore` (threadId-keyed SSE);
  the Activity monitor manually cross-seeds them
  (`app/Views/Activity/Monitor/ActivityMonitorView.swift:273-299`).
- **Run controls** (`pause`/`resume`/`stop`/`delete` —
  `app/Views/Activity/ActivityViewHelpers.swift:133-153`) fire the endpoint and flip
  **no** local state; `resumeWorkflow`'s returned thread is discarded; paused runs
  are never SSE-subscribed (`ActivityMonitorView.swift:287-296`), so a Resume can
  never visibly succeed.

### 1.4 Status vocabularies

Server: `TERMINAL_STATUSES = {completed, error, failed, cancelled, stopped}`
(`fs/workflows/run_status.py:21`) — `error` and `stopped` are never written by any
code path; the docstring admits it is a superset of unreconciled synonyms.
Client: **four** disjoint enums (`WorkflowStatus` 5 cases, `NodeExecutionStatus` 5,
`ExecutionThread.status` 9, `ActivityRunStatusType` 5) with three lossy maps —
unknown raw status → `.running` (`app/Views/Activity/ActivityViewHelpers.swift:103`)
and user-cancelled → `.failed` red ✗
(`app/Services/WorkflowExecutionObserver.swift:124-148`, `WorkflowStatus` has no
`.cancelled`).

---

## 2. Fragility findings, ranked

### P0 — data loss / permanently stuck state

| # | Finding | Evidence |
|---|---|---|
| F1 | Artifact `run_id`/`step_name` never populated on the live path → run↔artifact link structurally broken; `/threads/{id}/run.run_artifacts` always `[]` | `llm_base.py:600` ← `state.get("task_id")`; `runtime.py:144`; `runner.py:902`; `threads.py:236-242` |
| F2 | Cancelled/failed/resumed runs never complete their documents → `Status.processing` forever (permanent spinner, no recovery path) | `runner.py:1314-1333` success-only; cancel `:1000-1010`; excepts `:1391,1444`; `core.py:413` resume never imports completion |
| F3 | `paused` is a dead-end: cancel is a silent no-op, DELETE 409s, stale-run recovery ignores it, resume 404s without a checkpoint | `threads.py:711,601-608`; `activity_store.py:483`; `core.py:446-450`; same for `accepted` if the worker thread dies pre-`runner.py:635` |
| F4 | Run snapshot overwrite destroys per-node config/prompt/provider/model 3s after `/execute` saved the full nodes | `core.py:333-341` saves full; `runner.py:673-680` overwrites trimmed; `COALESCE(EXCLUDED…)` `activity_store.py:936` |
| F5 | Reopening a library mid-run flips the live run `running→failed` (cutoff-less stale sweep on every ActivityStore construction) then back to `completed` | `fs/workflows/activity.py:739` + `activity_store.py:648` (`started_before=None`) |

### P1 — the user cannot see or control what's happening

| # | Finding | Evidence |
|---|---|---|
| F6 | Content pane stale after workflow writes: splice lands in `childrenCache`, accessors read `currentDocuments`; reader pane has no refresh hook; inspector refresh gated on local-process SSE counters | §1.3; `DocumentInspectorContentV2.swift:33-35,73-80,321-327`; `PageContentPane.swift:7-39` |
| F7 | Run controls are fire-and-forget: no optimistic state, no re-subscribe on resume, delete leaves the row, Monitor vs Detail expose different button sets (different enums) | `ActivityViewHelpers.swift:133-153`; `ActivityMonitorView.swift:256-296` vs `ActivityDetailView.swift:185-210,367-375` |
| F8 | Cancel latency unbounded (checked only between LangGraph events; a long vision call can't be interrupted); batch uses a different, better `asyncio.Event` mechanism — two implementations of the same verb | `runner.py:937-1035`; `fs/execution/batch.py:562-593` |
| F9 | Monitor per-file rows vanish the instant a node finishes; nodes with unrecognized ids are hidden entirely; nodes sorted by id string, not execution order; terminal node states are fabricated client-side | `ActivityMonitorModel.swift:73-75,111-139,155-187`; `WorkflowExecutionObserver.swift:159-172` |
| F10 | Runs without checkpoints are invisible: `GET /threads` enumerates from `checkpoints`, not `workflow_runs` (`list_workflow_runs` has zero callers); batch item runs write no `workflow_runs` row at all | `threads.py:523`; `activity_store.py:1112`; `batch.py:561` |
| F11 | 16 palette tools have no implementation and kill the whole graph at build; served unfiltered to the editor | `registry_builtins.py:185-848`; `workflows.py:365-372`; `builder.py:472-474` |

### P2 — comprehension, quality, drift

| # | Finding | Evidence |
|---|---|---|
| F12 | Editor semantics invisible: unified port points collapse parallel edges into one line; data-type icons dev-gated; edge labels always null in shipped presets; fan badges hardcoded and wrong (zoom omitted, transcribe spurious); drop ignores zoom/pan transform; node drag mutates neighbours and autosaves the drift | `WorkflowCanvasView+EdgeConnection.swift:7-21,228-233`; `WorkflowEdgeView+Helpers.swift:32-58`; `WorkflowCanvasView.swift:153-176`; `+Gestures.swift:96-113`; `WorkflowEditor.swift:190-205` |
| F13 | Execution order never shown on canvas/table (topo sort exists but only the dev-gated list view uses it); raw `(x, y)` pixels shown as user data | `WorkflowEditor+NodeViews.swift:66-104,152-157` |
| F14 | Artifact list order is alphabetical-by-type, not pipeline order; artifact routes have no `run_id`/`step_name` filter; listing is full-scan + Python sort (fake pagination); `Artifact` has no sequence field and naive-local `created_at` | `ArtifactListView.swift:52-62`; `fs/api/routes/document/artifacts.py:250-352`; `models/__init__.py:599` |
| F15 | Default-workflow duplication regrown: 8 transcription presets (HTR and Paleography topologically identical); Catalogue in three shapes; internal `Spanish Script v2 Child Passes` leaks into the Run menu with no source node; `Export to Desktop` has zero edges | preset JSONs; `default_workflows.py:32-46` |
| F16 | Fresh-install `$medium` = paid `openrouter/openai/gpt-4o-mini` (tables triplicated in `api/main.py:352-372`, `db/app.py:830-839`, `settings.py:348-357`); preflight validates aliases/capabilities but never credentials; the flagship Catalogue's `citations_extract` uses `$medium` → mid-run node failure on a keyless install; Apple-failure fallback chain is empty by default (paid fallbacks off) | `llm/__init__.py:665-716,1004-1035`; `workflows/validation.py:230-320`; `catalogue.json:116-123` |
| F17 | LangChain is a black box: zero callbacks/tracing/verbose repo-wide; only token totals via `_record_usage` (`llm/__init__.py:212-252`); no prompt/response/retry/latency capture; no cost on any normal run (cost code exists only in `model_comparison.py`) | repo-wide grep; `llm/model_types.py` vs `model_comparison.py:182-329` (2024-stale hand pricing table, duplicated cost engines) |
| F18 | Sub-workflow refs resolve from shipped JSON, ignoring DB edits (`subworkflow.py:103-125`); `Transcribe (Auto-Detect)` relies on empty-target route_map edge inference (`builder.py:455-468`) and must disable parallelism in its own smoke test | `test_default_workflow_e2e_harness.py:243` |
| F19 | All "E2E" default-workflow tests stub the model (`_install_generic_tool_smoke_stubs`); nothing exercises a real provider/credential path; no health surface answers "does my configured model work" (`provider_validation.py` is a save-time regex; `wrap_provider_call:182` is dead code) | `test_default_workflow_e2e_harness.py:215-256,487`; `api/main.py:1123-1186` |
| F20 | Activity plumbing races: fire-and-forget activity saves silently drop with no loop (`activity.py:135-141`); every SSE event triggers a full 100-item run-list rebuild (acknowledged `#3231 p3`, `ActivityStore.swift:52-54`); archive delays (1s/30s) leave `isAnyWorkflowRunning` stale (`WorkflowExecutionObserver.swift:141-193`) | as cited |

---

## 3. Target design per scope area

### 3.1 Results surfacing (final result → content pane, live refresh)

**Server.**
1. Introduce an explicit **run-result contract**: each workflow's terminal
   content-producing node's output is recorded on the run
   (`workflow_runs.result_artifact_ids` or a `run_outputs` list in
   `completion_metadata`) at the completion boundary
   (`complete_run_documents` is the right seam — it already owns the status flip and
   the change-event emit).
2. Call `complete_run_documents` (or a `finalize_run_documents(status)` variant that
   flips `processing → pending` on failure/cancel) from **every** terminal path:
   success, failure, cancel, resume. This kills the permanent-spinner class (F2).
3. Emit `document.updated` when `page_content` changes mid-run (in
   `_save_artifact_sync` after the doc save), not only at run completion — the
   change-stream substrate on the client already coalesces bursts.

**App.**
4. One rule: *views resolve documents through the store, never hold `Document`
   snapshots*. Concretely: `refreshedDocument(_:in:)` must search `childrenCache`
   (and `collections`) in addition to `currentDocuments`; `handleCurrentDocumentsChange`
   gets a `childrenCache` counterpart or — simpler — `detailDocument`/
   `pageFocusDocument` become id-based lookups into the store.
5. Retire the local-SSE-counter refresh gate in `DocumentInspectorContentV2` in
   favor of the change stream (it already reaches `DocumentStore.apply`).

### 3.2 Provenance-first artifact browser

**Data model** (all additive, `_ensure_table` picks up new Pydantic fields on fresh
DBs; persisted DBs need an idempotent ALTER per Rule 9):
- Populate `run_id` with the run's `thread_id` and `step_name` with the node id +
  display label. The one-line root fix is in `build_initial_state` /
  the runner (put `thread_id` into state; pass node identity through the fan-out
  shim already at `builder.py:1078,1219`) plus `_save_artifact_sync` writing both.
- Add `workflow_id`, and a per-run monotonic `sequence` (the runner already numbers
  file steps — `file_index` at `runner.py:783-796`).

**API.** `GET /api/artifacts?run_id=…&step_name=…` filters; DB-side ORDER/LIMIT
instead of full-scan Python sort (F14).

**Browser UX.** Group artifacts by run (newest run first), within a run by step
sequence; each row shows step label · provider·model · duration; artifact detail
gets a "Produced by" section whose run link opens the Activity run and whose step
link highlights the node in the run trace (§3.3). This is exactly the shape #4284
asks for; #2277's "click a step → jump to comparison" composes on top.

### 3.3 Per-step inspectability (the executed-run trace)

Feasibility: **high — most data exists, three leaks to plug.**
- *Topology*: `_planned_steps_from_run` already derives upstream/downstream per node
  from `workflow_snapshot` (`threads.py:204`); Mermaid render exists.
- *Timing/status*: `progress_timeline` has per-node and per-file steps.
- *State history*: `GET /threads/{id}/history` walks checkpoints.

Plug: (a) stop the snapshot overwrite (F4) — persist the full node dicts including
`config`/`provider_name`/`model_name`, so the trace can show the prompt and model
actually used; (b) stop compacting away step outputs — persist each node's output as
a run-scoped artifact instead (this *is* #4284: per-step artifacts make the
checkpoint compaction harmless); (c) flush `progress_timeline` incrementally (per
node boundary), not only at terminal states.

Then the app's "run trace" view is a **read-only canvas** rendering
`workflow_snapshot` nodes colored by `progress_timeline` status, with per-node
detail (input counts, duration, provider/model, output artifact links, error). It
is distinct from the editor (which deliberately shows no run state —
`WorkflowCanvasView.swift:43-52`); the existing dead progress-badge code
(`WorkflowNodeView.swift:58-84`) can be revived inside this read-only surface.
Cost/tokens per step requires threading `_record_usage`'s contextvar collector
(`llm/__init__.py:212-252`) into the per-node timeline — the collector exists,
nothing drains it per node today (F17).

### 3.4 Activity model + controls

**One status vocabulary.** Server: normalize to
`accepted | running | paused | completed | failed | cancelled` (write `cancelled`,
never `stopped`/`error`), regenerate OpenAPI, and give the app ONE generated enum
replacing the four hand-rolled ones (this also fixes cancelled-shows-as-failed).
**Recover every non-terminal status**, with an age cutoff, and only from the
background sweep (fix F3/F5): `accepted` and `paused` past a deadline → `failed`
with a reason; drop the cutoff-less sweep from `_init_database`.
**Make controls transactional in the UI**: each control awaits the POST, applies the
returned state (resume already returns the fresh `ExecutionThread` — stop discarding
it), re-subscribes SSE for any non-terminal run regardless of current status, and
removes rows on delete. Unify Monitor/Detail on one `RunControls` component.
**Unify cancel/pause on the batch mechanism** (`asyncio.Event`, checked pre-node and
per-file) and add a per-node timeout so cancel latency is bounded (F8).
**Keep completed runs inspectable**: per-file rows should persist after node
completion (they're in `progress_timeline`; the monitor just drops them — F9).

### 3.5 Node editor: type system + comprehensibility

Simplifications, in order of leverage:
1. **Ship the semantics that already exist**: un-gate per-port geometry and
   data-type icons from the dev tier (unified-port mode is what makes parallel
   edges invisible — F12). Fan badges should derive from the registry's
   `supports_batch`/port cardinality, not name allowlists.
2. **Type the vocabulary once, server-side**: the registry already knows each tool's
   ports and `DataType`; emit it in OpenAPI so the app's three duplicated
   string-switches (color/icon/mapping) collapse into one generated mapping.
   Kill the lenient `WorkflowEdge` decoder defaults (`WorkflowTypes.swift:269-284`).
3. **Placement**: fix drop-location transform (inverse of scale/offset); stop
   mutating neighbours during drag; add "Tidy" auto-layout (left-to-right layered
   by the existing topo sort — `WorkflowEditor+NodeViews.swift:66-104`) instead of
   trusting hand-set coordinates; show step numbers on the canvas from that same
   sort. Extends #4178 / #2524 / #1660.
4. **Zoom step visualization**: `zoom` (`fs/workflows/tools/zoom.py:130-143`) is a
   1→N tile expansion with a rich config schema and no dedicated UI. Give it a
   NodeConfig with a live preview (tile grid over a sample page thumbnail — rows ×
   overlap × scale are all computable client-side) and a proper fan-out badge.
   With #4309 (first-pass text bounding boxes, W3C-annotation-shaped), zoom gains a
   real region target: tiles can align to detected text lines instead of blind
   strips. The persistence seam already exists — `Artifact.ocr_geometry:
   OCRGeometryResult` (`fs/models/__init__.py:585`) and `save_artifact`'s
   `ocr_geometry` parameter (`llm_base.py:466`) — #4309 is about populating it on
   every vision pass and consuming it (transcript↔image highlight, zoom targets).
5. **Palette honesty**: filter unimplemented tools out of `/tools` (+ a contract
   test that palette == executable) — F11.

### 3.6 Comparison as a first-class node (design level; another lane implements)

Findings that reframe the ask:
- A `model_comparison` **workflow node already exists and is registered**
  (`fs/workflows/model_comparison.py:1222-1303`), with REST (14 endpoints under
  `/model-comparison`), CLI, and a full SwiftUI surface
  (`app/Views/Chat/ModelComparison/`, 11 files) including a workflow-editor bridge
  (`NodePopover+Comparison.swift` → `NodeComparisonSheet`). It is beta-tier
  (`FeatureTiers.generated.swift:210-216`), and "New Comparison" is already in the
  sidebar Add menu (`app/App/Menus/AddItemMenu.swift:79-82`) — hidden only by tier.
- The gaps are: (A) the node takes only `prompt`/`system_prompt` TEXT ports — no
  `files`/`documents`, so it can't compare per-document work inside a graph;
  (B) results are process-memory only (`comparison_history`,
  `model_comparison.py:335`) — nothing persists, lost on restart, leaks across
  libraries; (C) hardcoded 2024 default models and a stale hand-rolled pricing/tier
  table (`:182-256,1295-1298`); (D) an unrelated image tool already occupies
  `artifact_type="comparison"` (`fs/workflows/tools/compare.py:39`).
- Design: widen the node's ports (files/documents + `mode: text|vision|tool`
  routing to the existing `compare_vision`/`compare_tool` engine methods), persist
  each comparison as an artifact (distinct artifact_type, e.g.
  `model_comparison`), make `ModelSpec` alias-aware (`$small`/`$vision_*`), and
  default `models` from `_configured_models` as `GET /presets` already does.
  Sidebar creation exists — promoting the tier + saved-comparison persistence
  covers #2526/#1753. No new registry machinery needed.

### 3.7 Default workflows + AI presets

- **Prune/merge the transcribe family** (8 presets; HTR ≡ Paleography topologically)
  per #3907/#3906/#3804; hide the internal `Spanish Script v2 Child Passes`
  (`is_template/is_system` misuse — it has no source node and fails standalone).
- **Fix structural oddities**: `Export to Desktop` with zero edges; Auto-Detect's
  empty-target route edge; sub_workflow's disk-only resolution (DB-backed resolver,
  `subworkflow.py:103-125`).
- **Presets**: alias resolution (`$small/$medium/$large`, `$vision_*` —
  `llm/__init__.py:346-349,665-716`) is sound and fails loud when unset, but
  (a) the seeded `$medium` is a paid provider used by the flagship Catalogue,
  (b) preflight never checks credentials, (c) paid fallbacks are off so the
  Apple-failure fallback chain is empty, (d) the tier-default table exists in
  triplicate. Target: one tier-default table; preflight extends to
  credential-presence; fresh-install defaults keep every default workflow fully
  on-device (feed into #4307's unified models list).
- Delete the dead `$APPLE_INTELLIGENCE` sentinel machinery
  (`default_workflows.py:216-268`) and the broken parallel vocabulary in
  `action_library.py` (references nonexistent `extract_text`/`web_search`).

### 3.7b Use the framework before building machinery (#4310)

Explicit assessment against LangChain/LangGraph's native capabilities:

- **Streaming events — already adopted, then discarded.** The live runner consumes
  `astream_events(version="v2")` (`fs/execution/runner.py:932`) — the framework's
  per-step event stream is exactly what feeds the SSE hub today. The run-trace gap
  (§3.3) is not "missing events" but that their payloads are compacted out of
  checkpoints (`types.py:27-47`) and the timeline is flushed only at terminal
  states. So #4310's "streaming events" item is ~free: keep the events, persist
  what they carry.
- **Checkpointing/interrupts — half-adopted.** Checkpoints are wired
  (`AsyncDuckDBCheckpointer`, `runtime.py:98`) and `/execute` accepts
  `interrupt_before/after` (`runner.py:869-897`), but pause/cancel bypass the
  framework entirely with process-local dict flags (`runner.py:937-1035`, F3/F8).
  LangGraph's native interrupt + checkpoint-resume is the intended mechanism for
  pause; adopting it makes "paused" a resumable checkpoint state instead of a dead
  coroutine, and cancel can wrap the stream's task rather than polling a flag.
- **Callbacks/tracing — unused (F17).** No callback handler anywhere; per-node
  cost/prompt/latency for the trace view should be a LangChain callback (or the
  `usage_metadata` already read at `llm/__init__.py:1518-1529`) drained per node,
  not new bespoke instrumentation.
- **Structured output & retry/fallback — partially adopted.** `chat_structured*`
  exists; retries are `max_retries=10` on every model (`llm/__init__.py:3948`) with
  a custom Apple-only fallback ladder (`:959-1035`) — a candidate for LangChain's
  `with_fallbacks`, which would also make the fallback policy visible/configurable.

Bottom line for #4310: the run-trace view (§3.3) and honest pause (§3.4) should be
framework adoption first, custom machinery only where LangGraph stops (artifact
persistence, provenance fields, the health surface).

### 3.8 Testing & health visibility

What exists is strong on graph wiring (parametrized preflight gate + stubbed E2E
over every preset — `test_default_workflows.py:1743`,
`test_default_workflow_e2e_harness.py:215`) and empty on reality: every E2E stubs
the model; provider validation is a save-time regex; no endpoint answers "what
works right now".

Target, three layers:
1. **Fixture-library E2E lane** (opt-in, `verify_perf.sh`-style): run each default
   workflow end-to-end against `seed_test_library.py` + `test-fixtures/files/` with
   the real local provider (Apple/MLX); assert artifacts + page_content + run status
   + provenance fields land. Gold-CER paleography calibration is #3905/#4144.
2. **Tool-level checks**: one canned invocation per registered tool (the registry
   knows ports/config schemas — generate the harness), plus the palette==executable
   contract test.
3. **Health surface**: `GET /api/health/ai` — per configured provider: key present,
   reachable (cheap live ping, cached), per tier: resolves + capability OK; per
   tool: implemented + `tested` flag. App renders it as a status view
   (Settings → AI or the status island), so "paleography needs a vision provider
   you haven't configured" is visible *before* a silent run. This also gives
   LangChain observability a home: an opt-in callback handler recording per-call
   prompt/model/latency/tokens into the run trace (§3.3), replacing the black box
   (F17).

---

## 4. Tracker cross-reference

Already filed and directly extended by this review (drafts say "extends #NNN"):
#4284 (per-step artifacts — §3.2/3.3), #4283 (paleography ran, nothing observable —
F2/F6/F16), #4276/#4277 (provider menu cache / recipes-vs-runs design), #4292/#4293
(workflow sidebar routing/chevron — out of this review's core but adjacent),
#4290/#4192 (library canvas — distinct surface from the workflow canvas; not
addressed here), #4229 (drop highlight — unrelated, confirmed not workflow),
#4186 (default-workflow tree heal), #3804/#3907/#3909/#3906 (defaults consistency),
#3905/#4144 (paleography validation fixture), #2526/#1753 (comparison at sidebar
level), #2524/#2440-#2443/#1660/#4178 (node editor comprehensibility), #1818 (cost
up front), #1832/#1830/#1831 (provenance + delete-by-run epic), #2277 (activity
columns + step→comparison), #4136-#4138 (cancel/SSE fragility), #1668 (checkpoint
reports artifacts but zero rows — same family as F1), #3387 (prior steps don't
update content — F6's oldest report), #3181 (chains in-memory), #4101/#4102
(sidebar workflow ids/sections), #4268/#4269 (activity visibility / error
surfaces), #4302-#4304/#4306/#4307 (new AI-defaults/MLX/embeddings cluster — §3.7
feeds #4307), #4309 (first-pass bounding boxes — the `ocr_geometry` seam exists,
§3.5), #4310 (langchain/langgraph capability audit — assessed in §3.7b: events
adopted-but-discarded, interrupts unused for pause, callbacks absent).

Notable *gaps* with no existing issue: F1 (run_id/step_name never populated),
F2/F3 (stuck processing docs; paused dead-end), F4 (snapshot overwrite), F5
(library-reopen flips live runs), F11 (phantom palette tools), F16 (fresh-install
$medium paid + no credential preflight), F19 (health surface), status-vocabulary
unification, and the run-trace view itself.
