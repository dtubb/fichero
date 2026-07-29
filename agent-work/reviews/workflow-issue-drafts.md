# Issue drafts — workflows & results surfacing (2026-07-29)

Source review: `agent-work/reviews/workflow-results-review.md` (finding ids F1-F20).
Manager files these; none created yet. Each: Title / Labels / Milestone / Body /
extends. Ordered by the epic's sequencing (draft 0).

---

## 0. EPIC: Every run tells you what it did — provenance, trace, and honest controls

**Labels:** type:feature, both, area:workflows, area:activity
**Milestone:** Workflows

**What.** Umbrella sequencing the runs-and-results overhaul so a non-technical user
can always answer: did it run, what is it doing now, what did each step produce,
where did the result go, and can I stop it.

**Why.** Review 2026-07-29 (agent-work/reviews/workflow-results-review.md) found the
provenance chain severed at the source (artifact `run_id` never populated), results
landing only in artifacts with a content pane that doesn't refresh, pause as a
dead-end state, and a node editor whose semantics are dev-gated off. #4283 is the
lived symptom; #4284 and #1832 already point at the destination.

**Sequencing (each step ships alone):**
1. Provenance plumbing: draft 1 (run_id/step_name/sequence) + draft 2 (stop the
   snapshot overwrite) — everything else reads this data.
2. Lifecycle honesty: draft 3 (complete docs on every terminal path) + draft 4
   (status vocabulary + recovery) + draft 5 (bounded cancel/pause).
3. Surfacing: draft 6 (content-pane refresh) + draft 7 (provenance-first artifact
   browser, extends #4284) + draft 8 (run-trace view).
4. Controls & activity UI: draft 9 (transactional run controls) + monitor fixes.
5. Editor comprehensibility: drafts 10-11 (extends #4178/#2524).
6. Defaults/presets/testing: drafts 12-15 (feeds #4307; extends #3907/#3905).

**Acceptance:** running the paleography ensemble on one page yields — a run row that
appears immediately, per-step artifacts ordered and attributed, a trace view showing
each node's model/prompt/duration/output, the final transcription visible in the
content pane without reselecting, and Stop/Pause/Resume that visibly work.

extends #1832 (provenance + reversible output EPIC), #4283.

---

## 1. Workflow artifacts never carry their run or step — populate run_id/step_name/sequence on the live path

**Labels:** type:bug, backend, area:workflows
**Milestone:** Workflows

**What.** `Artifact.run_id` and `step_name` exist (`fs/models/__init__.py:589,592`)
but the live `/execute` path never sets them: `_save_artifact_sync` writes
`run_id=task_id` (`fs/workflows/tools/llm_base.py:600`) and `task_id` is never put
into state by `build_initial_state` (`fs/workflows/runtime.py:144-163`) or the
runner (`fs/execution/runner.py:902-907`). Only scheduler/file-watcher set it — to a
UUID unrelated to any thread (`fs/workflows/builder.py:1879`). Consequence:
`GET /threads/{id}/run.run_artifacts` is always `[]` (`threads.py:236-242`),
`node_name` always null, and no artifact can be traced to its run/step.

**Design sketch.** Put `thread_id` into initial state as the run id; thread node
identity through the fan-out shim (`builder.py:1078,1219` already propagate the
key); `_save_artifact_sync` writes `run_id=thread_id`, `step_name=node id`, plus a
new `workflow_id` and per-run `sequence` int (runner already numbers file steps,
`runner.py:783-796`). Fresh DBs pick the new fields up via `_ensure_table`;
persisted DBs need an idempotent ALTER (Rule 9). Add `run_id`/`step_name` filters to
`GET /api/artifacts` while there.

**Acceptance:**
- [ ] A live run's artifacts all carry `run_id == thread_id`, `step_name`, `sequence`.
- [ ] `GET /threads/{id}/run.run_artifacts` non-empty for a run that produced artifacts (regression test).
- [ ] `GET /api/artifacts?run_id=` filter works, DB-side.

extends #4284, #1668.

---

## 2. Run snapshot overwrite destroys the prompt/model actually used

**Labels:** type:bug, backend, area:workflows
**Milestone:** Workflows

**What.** `/execute` saves the full node dicts on the run
(`core.py:333-341`), then the runner overwrites `workflow_snapshot` with a trimmed
`{id, tool, label}` projection (`fs/execution/runner.py:673-680`);
`COALESCE(EXCLUDED…)` (`activity_store.py:936`) lets the overwrite land. Per-node
`config`, `inputs`, `provider_name`, `model_name` — the prompt and model actually
used — are permanently lost from the run record, surviving only while the live
Workflow row is unedited.

**Design sketch.** Persist the full node dicts (or the trimmed shape PLUS
config/provider/model). Additionally flush `progress_timeline` at node boundaries,
not only terminal transitions (`runner.py:1381,1435,1489`) — a crash currently
loses the whole timeline.

**Acceptance:**
- [ ] After a run, `workflow_snapshot` contains each node's config/provider/model.
- [ ] Editing the workflow after the run does not change what the run record reports.
- [ ] Killing the process mid-run leaves a partial `progress_timeline`.

---

## 3. Cancelled, failed, and resumed runs leave documents at `processing` forever

**Labels:** type:bug, backend, area:workflows
**Milestone:** Workflows

**What.** `complete_run_documents` runs only on the success path
(`fs/execution/runner.py:1314-1333`); the cancel return (`:1000-1010`), both except
blocks (`:1391,1444`), and `resume_workflow` (`core.py:413` — never imports
completion) skip it. Content tools set `Status.processing` on each doc they touch
(`llm_base.py:634`), so any non-success outcome strands documents with a permanent
spinner that no later run repairs.

**Design sketch.** A `finalize_run_documents(final_status)` called from every
terminal path: success → `completed` (current behavior); failure/cancel → revert
`processing → pending` (or a distinct `interrupted`), still appending the provenance
entry with `result: failed|cancelled`. Resume must run the same boundary.

**Acceptance:**
- [ ] Cancel mid-run: touched docs return to a non-spinner state (test).
- [ ] Failed run: same. Resume-to-completion: docs complete.

extends #4136 (cancel doesn't stop executor), #4283.

---

## 4. Run status vocabulary: `paused`/`accepted` are dead-end states; unify the enums

**Labels:** type:bug, both, area:workflows, area:activity
**Milestone:** Workflows

**What.** Server: pausing returns from the worker coroutine leaving
`_running_workflows[tid]` at `paused` — cancel then silently no-ops
(`threads.py:711`), DELETE 409s (`threads.py:601-608` — paused not in
`DELETABLE_TERMINAL_STATUSES`), stale-run recovery only touches `running`
(`activity_store.py:483`), and resume 404s with no checkpoint (`core.py:446-450`):
a run paused before its first checkpoint is stuck forever. Same for `accepted` if
the worker thread dies early. `TERMINAL_STATUSES` contains `error`/`stopped` that
nothing ever writes (`run_status.py:21`). Client: four disjoint status enums with
lossy maps — unknown → `.running` (`ActivityViewHelpers.swift:103`), cancelled
rendered as failed (`WorkflowExecutionObserver.swift:124-148`).

**Design sketch.** One vocabulary:
`accepted|running|paused|completed|failed|cancelled`. Recovery sweeps every
non-terminal status past an age cutoff (and drop the cutoff-less sweep run on every
ActivityStore construction — it flips live runs to failed when a library is
reopened, `activity.py:739` + `activity_store.py:648`). Allow cancel/delete of
paused/accepted. Regenerate OpenAPI so the app uses one generated enum; delete the
three hand-rolled ones.

**Acceptance:**
- [ ] Pause → Cancel works; pause-before-checkpoint is cancellable/deletable.
- [ ] Reopening a library mid-run does not flap the run's status (regression test).
- [ ] Cancelled runs render as Cancelled, not Failed.

extends #4137, #4142.

---

## 5. Cancel/pause latency is unbounded; unify on the batch mechanism

**Labels:** type:bug, backend, area:workflows
**Milestone:** Workflows

**What.** Single-run cancel/pause are dict flags checked once per LangGraph event
(`runner.py:937-1035`) — a long vision call is uninterruptible, and after restart or
registry eviction (`runner.py:214-227`, which can evict a LIVE run via
`next(iter(...))`) the endpoints return `not_running` while the DB says running.
Batches already use a better `asyncio.Event` checked pre-node and per-file
(`batch.py:562-593`). `resume_workflow` additionally blocks the FastAPI loop with
`ainvoke` (`core.py:493`), emits no SSE, and force-writes `completed` ignoring
errors (`core.py:517-522`).

**Design sketch.** One cancellation primitive (event) shared by single runs and
batches, checked per-file inside fan-out; per-node timeout for bounded abort;
resume runs on the worker-thread path like `/execute` (reusing
`_run_workflow_in_background`) so it streams, checks flags, and hits the completion
boundary. Prefer LangGraph's native interrupt + checkpoint-resume for pause over
custom flags — checkpointing and `interrupt_before/after` are already wired
(`runtime.py:98`, `runner.py:869-897`) and unused for this (#4310).

**Acceptance:**
- [ ] Cancel during a multi-file node stops within one file boundary (test).
- [ ] Resume streams SSE and respects a subsequent cancel.

extends #4136, #4310.

---

## 6. Content pane does not refresh when a workflow writes page_content

**Labels:** type:bug, frontend, area:library, area:reader
**Milestone:** Workflows

**What.** The change-stream splice correctly lands fresh page children in
`childrenCache` (`DocumentStore+ChangeStream.swift:226-243`), but every content-pane
accessor reads only `currentDocuments`:
`DocumentInspectorContentV2.liveDocument` (`:33-35,325-327`) and the shell's
`refreshedFocusedDocument` (`ContentView+StatePreview.swift:135-157`), while
`detailDocument`/`pageFocusDocument` are `@State Document` snapshots
(`ContentView.swift:84,99`). `PageContentPane` has no refresh hook at all beyond its
`document` parameter (`PageContentPane.swift:7-39`). The inspector's refresh trigger
is gated on this process's SSE counters (`DocumentInspectorContentV2.swift:73-80`),
so CLI/MCP/other-window runs never fire it. Net: transcription results appear only
after reselecting the page (#3387 reported this in March). Server side, `document.updated`
is emitted only at successful run completion (`completion.py:184`) — mid-run
page_content saves emit nothing.

**Design sketch.** (a) `refreshedDocument(_:in:)` resolves through
`childrenCache` + `collections` too, or the shell keeps ids and derives the document
from the store; (b) replace the SSE-counter gate with the change stream; (c) server
emits `document.updated` from `_save_artifact_sync` when it writes page_content.

**Acceptance:**
- [ ] Run transcribe on a visible page: text appears without reselecting (UI-adjacent logic test on the resolver; manual pixel check).
- [ ] A CLI-launched run updates an open window the same way.

extends #3387, #4283.

---

## 7. Provenance-first artifact browser: group by run, order by step

**Labels:** type:feature, both, area:workflows, area:inspector
**Milestone:** Workflows

**What.** Artifacts read as dumped: the list sorts alphabetically by type then
newest-first (`ArtifactListView.swift:52-62`, duplicated at
`DocumentInspectorContentV2.swift:193-206`), `runId` is never rendered anywhere in
`Views/` (grep), "Workflow" in the detail is an unlinked `stepName` string
(`ArtifactDetailView.swift:113-118`), and the ensemble's three transcribe passes are
indistinguishable. Server listing is full-scan + Python sort with fake pagination
(`artifacts.py:265-352`).

**Design sketch.** Requires draft 1. Browser groups by run (workflow name + relative
time header), within a run ordered by `sequence`; rows show step label ·
provider·model · duration; detail gains "Produced by" linking run → Activity run
view and step → run-trace node (draft 8). Server: `run_id`/`step_name` filters and
DB-side ordering/pagination.

**Acceptance:**
- [ ] Ensemble run on one page shows its passes in pipeline order under one run group.
- [ ] Artifact detail navigates to its run.

extends #4284, #4278 (inspector section order), #2277.

---

## 8. Run trace view: read-only "what actually happened" graph per run

**Labels:** type:feature, both, area:workflows, area:activity
**Milestone:** Workflows

**What.** No surface shows a run's steps: `ThreadDetailContent` renders exactly
three fields (`WorkflowExecutionView.swift:216-312`), the editor deliberately shows
no run state (`WorkflowCanvasView.swift:43-52`), and the monitor drops per-file rows
the moment a node completes (`ActivityMonitorModel.swift:111-139`) and hides nodes
whose ids it doesn't recognize (`:73-75`).

**Design sketch.** Server already has topology (`_planned_steps_from_run`,
`threads.py:204`), timing/status (`progress_timeline`), and history (checkpoints);
drafts 1-2 add step→artifact links and true config/model. The view: a read-only
canvas of `workflow_snapshot` nodes colored by executed status, click a node → step
detail (inputs count, prompt, provider/model, duration, output artifacts, error).
Revive the editor's dead badge/pulse code (`WorkflowNodeView.swift:58-84`) here.
Per-step tokens/cost: drain the `_record_usage` contextvar collector
(`llm/__init__.py:212-252`) into the per-node timeline — the accounting exists,
nothing consumes it per node (no cost is recorded on any normal run today; the only
cost code lives in `model_comparison.py`).

**Acceptance:**
- [ ] Open a completed ensemble run → graph of executed nodes with durations and per-step artifact links.
- [ ] A failed run highlights the failing node with its error.

Assessment vs #4310: the per-step event stream is already consumed
(`astream_events` v2, `runner.py:932`) — most of the trace is framework-free-lunch
once drafts 1-2 stop discarding the payloads; per-step cost should be a LangChain
callback, not bespoke instrumentation.

extends #4284, #2277, #1818 (up-front estimate is the sibling: same per-node cost
model), #4310.

---

## 9. Run controls are fire-and-forget: no state update, no re-subscribe, divergent button sets

**Labels:** type:bug, frontend, area:activity
**Milestone:** Activity View

**What.** `performRunAction` fires the endpoint and flips no local state
(`ActivityViewHelpers.swift:133-153`; `ActivityMonitorView.swift:256-265`;
`ActivityDetailView.swift:367-375`); `resumeWorkflow`'s returned `ExecutionThread`
is discarded; paused runs are never SSE-subscribed (`ActivityMonitorView.swift:287-296`)
so Resume can never visibly succeed; Delete leaves the row and the subscription;
Monitor and Detail switch over different enums and expose different buttons
(`ActivityMonitorView.swift:182-221` vs `ActivityDetailView.swift:185-210`);
`endExecution` fabricates terminal node states (`WorkflowExecutionObserver.swift:159-172`).

**Design sketch.** One `RunControls` component over one generated status enum
(draft 4): await POST → apply returned state → (re)subscribe SSE for any
non-terminal run → remove row + unsubscribe on delete. Collapse the two live-run
stores (`WorkflowExecutionObserver` + `WorkflowExecutionStore`) into the
threadId-keyed one; the manual cross-seeding at `ActivityMonitorView.swift:273-299`
is the symptom.

**Acceptance:**
- [ ] Pause→Resume→Stop from the monitor visibly transitions each time (logic tests on the store reducer).
- [ ] Same controls in Monitor and Detail.

extends #4135, #4142, #4138.

---

## 10. Node editor: ship the semantics — ports, edge types, execution order, honest palette

**Labels:** type:bug, both, area:workflows
**Milestone:** Workflows

**What.** In the shipping build the graph's meaning is invisible: per-port geometry
and data-type icons are dev-gated, so all ports collapse to one point and parallel
edges (e.g. zoom→transcribe `files` + `documents`) render as a single line
(`WorkflowCanvasView+EdgeConnection.swift:228-233`; `WorkflowEdgeView+Edges.swift:11-32`);
edge labels are null in every shipped preset; fan badges come from hardcoded
tool-name allowlists that omit `zoom` (the real 1→N step) and decorate transcribe
edges spuriously (`WorkflowEdgeView+Helpers.swift:32-58`); execution order is never
shown on the canvas though a topo sort exists (`WorkflowEditor+NodeViews.swift:66-104`);
the table shows raw `(x,y)` pixels as user data (`:152-157`). Separately, 16
palette-visible tools have no implementation (`if/switch/loop/filter/merge/
to_pdf/to_word/to_excel/to_json/save_to_library/export/crop/enhance/rotate/segment/
custom_llm` — `registry_builtins.py:185-848`), served unfiltered
(`workflows.py:365-372`) and fatal at build (`builder.py:472-474`).

**Design sketch.** (a) Un-gate port geometry/data-type icons; derive fan badges from
registry port cardinality/`supports_batch`; offset parallel edges. (b) Emit the port
data-type vocabulary via OpenAPI and collapse the app's three duplicated
string-switches; make the `WorkflowEdge` decoder strict
(`WorkflowTypes.swift:269-284` currently defaults missing ports). (c) Step-number
badges on the canvas from the existing topo sort. (d) Filter `/tools` to
implemented + aliased tools, with a contract test that palette == executable.

**Acceptance:**
- [ ] Two parallel edges are visually distinct; zoom edges carry the fan badge.
- [ ] Every palette tool compiles into a runnable graph (test).

extends #4178, #2524, #2440, #2441, #2442, #2443, #1660.

---

## 11. Node placement: transform-correct drop, no neighbour mutation, tidy auto-layout, zoom-step preview

**Labels:** type:bug, frontend, area:workflows
**Milestone:** Workflows

**What.** Drop location ignores the canvas transform (`.onDrop` after
`.scaleEffect/.offset`, no inverse — `WorkflowCanvasView.swift:153-176`,
`+DropHandling.swift:36-73`); dragging one node pushes neighbours and autosaves the
drift (`+Gestures.swift:96-113`; `WorkflowEditor.swift:190-205`); "add node" appends
at rightmost-X on an arbitrary branch (`WorkflowInspector+DataLoading.swift:119-129`);
overlap resolution is a capped 10-iteration heuristic (`+DropHandling.swift:123-156`).
The `zoom` tool (`fs/workflows/tools/zoom.py:20-33,130-143`) has no dedicated config
UI — raw JSON-schema fields via `DynamicConfigView` — and no visual representation of
its tiling.

**Design sketch.** Inverse-transform drop coordinates; drag moves only the dragged
node; a "Tidy" command lays out left-to-right by the existing topo sort; add-node
places after the selected node, not rightmost. Zoom gets a NodeConfig with a live
tile-grid preview over a sample page thumbnail (rows/overlap/scale are pure client
math). With #4309's first-pass bounding boxes, tiles align to detected text lines
instead of blind strips — the `Artifact.ocr_geometry` seam already exists
(`fs/models/__init__.py:585`, `llm_base.py:466`).

**Acceptance:**
- [ ] Drop at cursor while zoomed/panned lands under the cursor.
- [ ] Tidy produces a readable layered layout of the ensemble preset.
- [ ] Zoom node shows its tiling visually.

extends #4178, #4309.

---

## 12. Default workflows: prune the transcribe family, fix structural defects, hide internal presets

**Labels:** type:bug, backend, area:workflows
**Milestone:** Workflows

**What.** 8 transcription presets ship; `Transcribe HTR` and `Transcribe
Paleography` are topologically identical (same 4 nodes / 7 edges, differing only in
vision/thinking mode and prompt). `Spanish Script v2 Child Passes` is an internal
component shipped `is_template/is_system=true` in `/Transcribe` — visible in Run
menus, no source node, fails standalone. `Export to Desktop` has zero edges and no
source node (works only by reading `selected_doc_ids`). `Transcribe (Auto-Detect)`
uses an empty-target route edge relying on builder inference (`builder.py:455-468`)
and must disable parallelism in its own smoke test
(`test_default_workflow_e2e_harness.py:243`). Sub-workflow refs resolve from shipped
JSON, ignoring DB edits (`subworkflow.py:103-125`). Dead code: the
`$APPLE_INTELLIGENCE` sentinel machinery (`default_workflows.py:216-268`, cites a
deleted file) and `action_library.py`'s parallel vocabulary referencing nonexistent
tools (`:400,417`).

**Design sketch.** Merge HTR/Paleography into one preset with a script parameter (or
prompt variants); add an `internal` flag (not folder placement) excluded from Run
menus and `direct_runnable`; give Export a source node; make Auto-Detect's routing
explicit edges; DB-backed sub-workflow resolver; delete the dead sentinel path and
fix/retire `action_library.py`'s builtin actions.

**Acceptance:**
- [ ] Run menu shows no internal/uncomposable presets.
- [ ] Preset-convention tests updated; `test_every_default_preset_passes_execution_gate` still green.

extends #3907, #3906, #3804, #4155, #4139, #4186.

---

## 13. AI tier defaults: keyless fresh install must run every default workflow; preflight checks credentials

**Labels:** type:bug, backend, area:ai
**Milestone:** Settings - Models & Providers

**What.** Fresh-install `$medium` is seeded `openrouter/openai/gpt-4o-mini`
(`api/main.py:361-362` — table triplicated in `db/app.py:830-839` and
`settings.py:348-357`), and the flagship Catalogue's `citations_extract` uses
`$medium` (`catalogue.json:116-123`): on a keyless install that node fails mid-run.
The preflight gate validates alias resolution and capability but never credential
presence (`workflows/validation.py:230-320`); missing keys surface as a construction
exception inside the node. The Apple-failure fallback chain is empty by default
(paid remote fallbacks off — `llm/__init__.py:1004-1035` — with `$small`/`$large`
both apple). Stale hardcoded model tables: `model_comparison.py:182-256` ("as of
2024" pricing/tiers, substring fallback → MID), node defaults `gpt-4o`/
`claude-3-5-sonnet-20241022` (`:1295-1298`), mixed-vintage defaults in
`llm/providers.py`.

**Design sketch.** One tier-default table (single source, imported thrice); seed
`$medium` on-device; extend `validate_workflow_llm_preflight` with
key-presence per resolved provider so the failure is a pre-run message, not a
mid-run node error; retire the hand-rolled pricing/tier tables in favor of the
litellm-backed `llm/model_types.py` path. Feeds the unified models list design.

**Acceptance:**
- [ ] Fresh install, no keys: every default workflow passes preflight and runs on-device.
- [ ] Missing-key case fails at preflight with the provider named.

extends #4307, #4302, #4276.

---

## 14. Default-workflow E2E lane against a real fixture library + tool-level checks

**Labels:** type:feature, backend, area:testing
**Milestone:** Testing Overhaul — Never Again

**What.** Graph-wiring coverage is strong (parametrized preflight gate,
`test_default_workflows.py:1743`; stubbed all-presets E2E,
`test_default_workflow_e2e_harness.py:215`) but every "E2E" stubs the model —
`_install_generic_tool_smoke_stubs` (`:487`), and the `FICHERO_INTEGRATION=1` tests
stub `resolve_model_alias` to fake (`tests/integration/
test_catalogue_workflow_execution_e2e.py:52-57`). Nothing exercises a real
provider, credentials, or prompt quality; only 4 tools carry `tested=True`.

**Design sketch.** An opt-in lane (`verify_workflows.sh`, gated like
`verify_perf.sh`): seed a fixture library (`seed_test_library.py` +
`test-fixtures/files/`), run each default workflow end-to-end on the real local
provider (Apple/MLX), assert run status, artifacts with provenance fields (draft 1),
and page_content landing. Plus a generated per-tool smoke harness (registry knows
ports/config schemas) and the palette==executable contract test (draft 10d). Red
runs feed `tests_to_issues.py`.

**Acceptance:**
- [ ] One command runs all default workflows against fixtures with a real local model; summary parseable, 0 failed required for release gate.
- [ ] Each registered tool has at least a canned-invocation check.

extends #3905, #4144, #4177, #3804.

---

## 15. AI health & observability: a status surface for providers/tiers/tools, and per-call LangChain visibility

**Labels:** type:feature, both, area:ai, area:activity
**Milestone:** Settings - Models & Providers

**What.** No endpoint answers "which providers/models/tools work right now":
`/api/health` reports document counts (`api/main.py:1123-1186`),
`provider_validation.py` is a save-time key-format regex (`:31-106`;
`wrap_provider_call:182` is dead code), and LangChain has zero observability — no
callbacks, tracing, or prompt/response logging repo-wide; only token totals via
`_record_usage` (`llm/__init__.py:212-252`). Debugging #4283-class failures means
guessing what prompt went out.

**Design sketch.** (a) `GET /api/health/ai`: per provider — key present, cheap
cached liveness; per tier — resolves + capability; per tool — implemented +
`tested`. (b) App: a health/status view (Settings → AI and/or status island) so
"paleography needs a vision provider" is visible before running. (c) An opt-in
LangChain callback handler recording per-call prompt, model, latency, retries,
tokens into the run's timeline (consumed by the run-trace view, draft 8) — this is
the "callbacks/tracing" leg of #4310; also consider `with_fallbacks` to replace the
custom Apple-only fallback ladder (`llm/__init__.py:959-1035`). Aligns with the
MLX/embeddings visibility cluster.

**Acceptance:**
- [ ] Health view shows red for an unconfigured vision tier; running paleography then warns pre-run.
- [ ] A run's trace shows each LLM call's model, latency, and tokens.

extends #4307, #4303, #4304, #4268, #4269, #4310.

---

## 16. Comparison node: document-aware ports, persisted results, current model defaults (design)

**Labels:** type:feature, backend, area:workflows, area:ai
**Milestone:** Workflows

**What.** Design-level (the agent/chat surface lane owns implementation around
chat). A `model_comparison` workflow node already exists and is registered
(`fs/workflows/model_comparison.py:1222-1303`), with 14 REST endpoints, CLI, a full
SwiftUI surface (`Views/Chat/ModelComparison/`, incl. the editor bridge
`NodePopover+Comparison.swift`), and a sidebar "New Comparison" entry gated at beta
tier (`AddItemMenu.swift:79-82`; `FeatureTiers.generated.swift:210-216`). Gaps: the
node takes only `prompt`/`system_prompt` TEXT ports — unusable in a `files → …`
graph; results live only in process memory (`comparison_history`,
`model_comparison.py:335`) — lost on restart, cross-library; defaults hardcode 2024
models (`:1295-1298`); `artifact_type="comparison"` is already taken by the image
compare tool (`tools/compare.py:39`).

**Design sketch.** Add `files`/`documents` input ports + `mode: text|vision|tool`
routing to the existing `compare_vision`/`compare_tool` engine methods; persist each
comparison as an artifact (`artifact_type="model_comparison"`) with run provenance
(draft 1); alias-aware `ModelSpec` (`$small`/`$vision_*`); default models from
`_configured_models` as `GET /presets` already does. Sidebar-level creation then
needs only the tier promotion + saved-comparison persistence.

**Acceptance:**
- [ ] A workflow can compare a page's transcription across 3 models and the results persist as ordered artifacts.
- [ ] No hardcoded model names remain in the node defaults.

extends #2526, #1753, #2277.

---

## Filing notes for the manager

- Use `scripts/file_issue.sh`; the area labels above map to the canonical 15 —
  adjust to the router's vocabulary (`backend`/`client:swiftui` lanes).
- Drafts 1-5 are backend-only and disjoint from the app lanes; 6, 9, 11 are
  Swift-only; 7, 8, 10, 15 are two-stack (OpenAPI regen per the Two-Stack Rule).
- Draft 16 should be filed but held for the agent-surface lane's sequencing.
- Overlap warnings: draft 4 touches `run_status.py`/`activity_store.py` which draft
  3 and 5 also read — dispatch 3/4/5 to one worker or sequence them.
