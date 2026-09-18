# Workflows — Design Spec (#4705 sibling; workflow surface)

> Milestone: workflows
> Manual: TBD — a section explaining: a workflow is a saved recipe of steps a user
> can run over selected files/folders/search results; the built-in ("Default
> Workflows") ones are locked and Duplicate-to-Edit makes an editable copy; the
> workflow bar lets a user build and run a short chain of verbs without opening the
> canvas at all; every run has a live output log and a history of past runs.

> Design-led (Testing Constitution). The creative director owns the intent below;
> tests enforce it; code makes them pass. **Status: DRAFT.**
>
> Grounded in code, read/grepped this session (paths relative to
> `fichero/fichero/` unless stated otherwise; server paths relative to
> `fichero-server/src/fichero_server/`). Also grounded in two prior read-only
> reviews carried into this spec as design evidence (not re-verified line-by-line
> here; flagged where a claim may have drifted since 2026-07-29/2026-08-02):
> `agent-work/reviews/workflow-results-review.md` (results/provenance/activity
> architecture review) and `agent-work/reviews/2026-08-02-node-editor-fabel-review.md`
> (canvas edge-legality review). See "Sources folded in" at the end.
>
> Tags: **[OK]** true today · **[BROKEN]** regression, code contradicts the
> intent · **[GAP]** intended, never built · **[PROPOSED]** decided here, not
> yet built.
>
> **Placement is not this spec's job.** Where the canvas, run log, and inspector
> RENDER (which pane, Preview vs Reader vs Library) is owned by
> `docs/contributor_manual/specs/ui/modes-to-panes.md` — read it for the ruling
> (canvas → Source/Preview, Reader = last/current run log, Inspector = palette ·
> node · runs, Library pane stays the navigator, panes never collapse by
> selection). This spec describes what a workflow node IS and DOES; cross-reference
> modes-to-panes rather than restating its matrix.
>
> **Test tags.** Swift `@Tag .workflow` already exists
> (`fichero/Tests/Unit/general/TestTags.swift:20`) and is reused, not
> reinvented, by this spec. `fichero-server/pyproject.toml`'s `markers` list has
> no per-surface markers yet (only `transport`, `build_config` follow the
> "spec:" convention) — add `workflows: … (spec: workflows)` there when the
> first backend pinning test for this spec lands.

## Intent (the design)

A **workflow** is a saved, named, ordered graph of **tool nodes** — each node one
capability (transcribe a page, clean text, translate, summarize, extract entities,
zoom into a region, …) wired input-to-output. A user reaches a workflow's
capability three ways, cheapest first: the **workflow bar** (build a short verb
chain over the current selection and run it without opening anything), the
**canvas editor** (open a workflow to see/change its whole graph), or a **saved
default workflow** (Fichero ships ~50 presets grouped into folders like
Transcribe/Clean Up/Translate — locked, Duplicate-to-Edit copies one to make it
editable). Running any of them produces a **run** with a live/replayable output
log. The surface lives in `Views/Workflow/**` (Editor, Canvas, Inspector,
Library, Execution) + `Services/WorkflowExecutionObserver.swift` on the client,
and `fichero-server/src/fichero_server/workflows/**` (registry, runtime,
builder, activity_store) on the engine.

## Prior art / best practices

Fichero's canvas follows the node-graph-editor pattern common to visual pipeline
tools (Node-RED, ComfyUI, Blender's shader editor): typed ports, drag-to-connect
edges, a side palette of available node kinds. The design commitment this spec
keeps testing for is the one those tools get right and Fichero's canvas
currently does not: **the editor must render the graph the engine will actually
execute**, not the editor's own idea of legality (2026-08-02 review, Finding 1).
The workflow bar is closer to a command palette / macro recorder (build a short
chain by clicking verbs, run once) — a lighter-weight entry point than the full
canvas, deliberately scoped to the current selection rather than a saved,
reusable graph. Locked defaults + Duplicate-to-Edit mirrors the common
"read-only template, editable copy" pattern (spreadsheet templates, Xcode
project templates) rather than versioned presets or a fork/PR model.

## What exists today (grounded)

**Canvas editor** — `Views/Workflow/Editor/WorkflowEditor.swift` hosts the
canvas plus an optional output log; its own doc comment says "canvas with
optional output log … goes in the content column, with WorkflowInspector in the
detail column" (`WorkflowEditor.swift:3-4`) — today's placement, superseded by
`modes-to-panes.md`'s Preview-pane ruling once that migration lands. The canvas
itself (`Views/Workflow/Canvas/WorkflowCanvasView*.swift`) draws nodes, edges,
ports, and handles drag/drop, gestures, and Mermaid diagram preview across 14
files. Locked default workflows refuse writes: `WorkflowSavePolicy.canAutoSave`
(`Views/Workflow/WorkflowSavePolicy.swift:8-10`) checks both the editor's and
the canonical sidebar copy's "is system" flag so a stale editor snapshot can't
sneak a save through; the server 403s every write to one regardless
(`WorkflowSavePolicy.swift:3-4` doc comment, #4514). `WorkflowToolbar.swift:27-52`
provides the **Duplicate to Edit** action for a locked preset, landing the copy
in a personal folder; `WorkflowEditor.swift:217-224` wires it and logs
`"Duplicated locked workflow to <id>"`.

**Tool palette / node config** — the node's own configuration surface (fields,
prompt, provider/model picker) is a fully-specced, APPROVED chapter of this
surface: `docs/contributor_manual/specs/ui/workflow-node-config.md`. It has no
`Milestone:` line of its own today; this Workflows spec is the natural home for
one once the two are reconciled (see "Sources folded in").

**Inspector** — `WorkflowInspector.swift` exposes two nested tab sets: the
top-level `WorkflowSurfaceTab` (Tools · Chain · Run, `WorkflowInspector.swift:56-83`)
and, inside Tools, `WorkflowInspectorTab` (Built-in · MCP · Agents,
`:32-53`) gated by `FeatureManager.isWorkflowToolsMCPEnabled` /
`isWorkflowToolsAgentsEnabled` (`:96-100`). This already matches
`modes-to-panes.md`'s ruling that the workflow inspector is "palette · node ·
runs" and is marked **[OK]** there.

**Run log** — `Views/Workflow/Execution/WorkflowOutputLog.swift` renders live
execution progress per node, reading `WorkflowExecutionObserver`'s persisted
state first so it survives view switches (`WorkflowOutputLog.swift:16-27`); it
deliberately excludes source tools (`files`, `collection`, `folder`, `search`)
from its per-file columns because they never emit file-level events
(`:29-35`).

**Workflow bar** — `Views/Shell/Toolbar/WorkflowBar.swift` is "the capability
bar — verbs that can act on what is selected" (`WorkflowBar.swift:3-4`):
Fichero ships ~90 tools and ~50 workflows and previously showed none of them
outside the canvas (`:6-11`); each verb's visibility is a projection of the
selection through the workflow's server-declared `accepted_inputs`, computed in
`WorkflowBarPolicy` with no SwiftUI so it is testable without a window (`:8-12`).
Clicking a verb **appends to an assembled chain rather than running immediately**
— "it shouldn't run right away, it should construct the chain" (`:39-41`,
attributed 2026-08-28) — the run is a deliberate press of the run button.
Folder order/icons for the bar's verb groups are server-declared, not
hard-coded client-side: `fichero-server/src/fichero_server/resources/workflow_folders.json`
lists 12 folders with `sort_order`/`icon` in the order the actual processing
route takes (image editing → detect segments → transcribe → clean up →
translate → describe → extract → catalogue → organize → books → convert →
export), explicitly so "a folder absent from this list sorts after the known
route and takes the fallback glyph, so a user's own folder still appears rather
than vanishing" (`workflow_folders.json:2`).

**Default/locked workflows and folders** — Default Workflows live under a
locked, system-seeded container folder; `Models/SidebarItem.swift:215-258` marks
that container and its subfolders `isLockedSystemFolder`/
`isDefaultWorkflowFolder` so the sidebar renders them purple and refuses drops
(`Models/Document.swift:597-606` `isLockedSystemNode`). `SidebarItemBuilder.swift:47-114`
computes which folder ids ARE that locked container so a preset workflow row
renders as read-only chrome without a per-row network round trip.

**Engine** — `fichero-server/src/fichero_server/workflows/` has ~30 modules:
`registry.py`/`registry_builtins.py` (tool catalog), `builder.py` (graph
construction from a `WorkflowDef`), `runtime.py`/`executor.py` (execution —
`executor.py` is flagged dead code by the 2026-07-29 review, test-only
importers), `activity_store.py`/`activity.py` (run rows, status, timelines),
`validation.py` (connection-legality rules the canvas is supposed to mirror),
`default_workflows.py` (seeds the presets), `subworkflow.py` (nested workflow
refs), `run_comparison.py`/`model_comparison.py` (the Compare Models feature).

## Behaviors (`workflows.*` ids)

### A. The canvas editor

- `workflows.canvas.renders-nodes-edges-ports` — **[PARTIAL]** (implemented,
  unpinned; #4797) the canvas draws every node, edge, and port for the
  workflow's graph (`Views/Workflow/Canvas/WorkflowCanvasView+NodesLayer.swift`,
  `+EdgesLayer.swift`, `WorkflowPortView.swift`).
- `workflows.canvas.locked-preset-is-read-only` — **[OK]** a locked default
  workflow cannot be saved from the canvas: `WorkflowSavePolicy.canAutoSave`
  refuses when either the editor's or the canonical copy's system flag is set
  (`WorkflowSavePolicy.swift:8-10`); the server also 403s the write
  independently. (The GitHub issue this originally shipped against has since
  been repurposed on GitHub for an unrelated, still-open "default workflow
  folders not visually protected" bug, so this line no longer cites a number.)
  Pinned: `WorkflowReadOnlySavePolicyTests`.
- `workflows.canvas.duplicate-to-edit` — **[PARTIAL]** (implemented, unpinned;
  #4797) duplicating a locked preset makes an editable copy in a personal
  folder and opens it for editing (`WorkflowToolbar.swift:27-52`,
  `WorkflowEditor.swift:217-224`).
- `workflows.canvas.edge-legality-matches-engine` — **[BROKEN]** the canvas's
  `canConnect` allows five conversions the engine's `validate_port_connection`
  rejects (`json→text`, `array→json`, `array→text`, `image→file`,
  `image→files`), so the canvas lets a user draw and save an edge the engine
  refuses only at RUN time (2026-08-02 review, Finding 1 — carried here as
  design evidence, not re-verified against current line numbers this session).
  ISSUE: #4478 ("Decide the six port conversions the old editor permitted —
  per-pair, from tool behaviour, engine-side only").
- `workflows.canvas.ports-come-from-registry` — **[BROKEN-partial]** the
  engine's tool registry is the source of truth for a node's ports
  (`enrich_node_with_ports`), but the canvas fabricates a fallback `files`
  input port when a node has no port data (`WorkflowPortView.swift`,
  `NodePopover.swift` per the 2026-08-02 review) — a second, client-owned copy
  of the tool contract that can silently disagree with the served one.
  **(#4736)** — filed 2026-09-18 with the exact behavior id as its title,
  found while mapping this milestone's issues; #2443 "Audit workflow node
  editor for parity with backend workflow capabilities" remains the closest
  umbrella, superseded here → #4736 is the precise tracking issue.
- `workflows.canvas.hidden-tools-in-palette` — **[GAP]** not every tool the
  engine can run appears in the canvas's node palette. ISSUE: #2440 ("Show the
  hidden tools").
- `workflows.canvas.16-palette-tools-cannot-execute` — **[BROKEN]** ~16
  palette-visible node kinds (`if`, `switch`, `loop`, `filter`, `merge`, the
  five export nodes, `custom_llm`, …) are declared in
  `registry_builtins.py` with no `@register_tool` implementation and served
  unfiltered by `GET /api/workflows/tools`, failing only at graph-build time
  (2026-07-29 review F11 — carried as design evidence, not re-verified this
  session). (#4746).
- `workflows.canvas.fan-out-editable` — **[GAP]** a node's fan-out (per-page vs
  whole-document) is an opaque property today, not something a user can see or
  change. ISSUE: #2442.
- `workflows.canvas.every-node-editable-tool` — **[GAP]** some node kinds are
  opaque (not backed by an editable tool config). ISSUE: #2441.
- `workflows.canvas.arrange-and-resize` — **[GAP]** no resize handles,
  trackpad pan, or "arrange"/"tidy" auto-layout commands on the canvas. ISSUE:
  #4340.
- `workflows.canvas.version-history` — **[GAP]** no snapshot/diff history of a
  workflow's definition changes over time. ISSUE: #4342.
- `workflows.canvas.dry-run` — **[GAP]** no "Test / Dry Run" affordance to
  validate a workflow before spending a real run. ISSUE: #4370.
- `workflows.canvas.cost-estimate-up-front` — **[GAP]** no shown cost/call
  estimate before running from the editor. ISSUE: #1818.

### B. Tool/node configuration

- `workflows.node-config.*` — see `docs/contributor_manual/specs/ui/workflow-node-config.md`
  (APPROVED — the ratified, shipped node-popover chapter of this surface;
  its F1–F16 findings and behavior ids are the authoritative source for field-
  and prompt-level behavior and are not restated here).

### C. Running and the run log

- `workflows.run.output-log-live` — **[PARTIAL]** (implemented, unpinned;
  #4797) `WorkflowOutputLog` shows live per-node execution progress, reading
  persisted `WorkflowExecutionObserver` state first so it survives a view
  switch (`WorkflowOutputLog.swift:16-27`).
- `workflows.run.source-tools-excluded-from-file-columns` — **[PARTIAL]**
  (implemented, unpinned; #4797) source tools (`files`, `collection`,
  `folder`, `search`) are excluded from the output log's per-file columns
  because they emit no file-level events (`WorkflowOutputLog.swift:29-35`).
- `workflows.run.scope-widening-confirmed` — **[OK]** a resolved run scope that
  would widen beyond the user's selection is parked for confirm/cancel rather
  than run silently (`Views/Workflow/Editor/WorkflowEditor.swift:33-40`,
  `+Actions.swift`). Fixed #4396/#4523 (closed 2026-09-18 — verified against
  code, not just the tag). Pinned: `WorkflowEditorRunGateTests`.
- `workflows.run.wrong-scope-runs-whole-folder` — **[OK]** (was BROKEN,
  re-verified 2026-09-18) running a workflow on one selected file no longer
  runs it over the whole containing folder: the confirm gate specifically
  covers the "empty selection on a `.collection`-input workflow" case this
  behavior named, and the dispatched run uses the CONFIRMED scope rather than
  re-resolving it. Pinned: `WorkflowEditorRunGateTests`.
- `workflows.run.provenance-run-id-on-artifacts` — **[GAP]** artifacts carry
  `run_id`/`step_name` fields but the live execution path never populates them
  (2026-07-29 review F1 — carried as design evidence; the "Runs on N documents"
  provenance ruling from the workflows-done-right mandate depends on this).
  ISSUE: #4312 (EPIC: "Every run tells you what it did — provenance, trace, and
  honest controls").
- `workflows.run.pause-is-dead-end` — **[GAP]** a paused run cannot be
  cancelled, deleted, or reliably resumed (2026-07-29 review F3). Folded into
  #4312.
- `workflows.run.stuck-processing-on-cancel-fail` — **[GAP]** a
  cancelled/failed run can leave its documents at `processing` forever, never
  calling the completion path that flips status back (2026-07-29 review F2).
  Folded into #4312.
- `workflows.run.controls-are-fire-and-forget` — **[GAP]** pause/resume/stop
  buttons fire the endpoint and apply no local state update, so Resume can
  appear to do nothing (2026-07-29 review F7). Folded into #4312.
- `workflows.run.trace-view` — **[GAP]** no read-only "what actually happened"
  per-run trace view exists yet, though the review found most of the needed
  data (checkpoints, `progress_timeline`, Mermaid diagrams) already persisted
  — three leaks to plug, not new architecture (2026-07-29 review §3.3). ISSUE:
  #4312 (trace is one leg of the EPIC).
- `workflows.run.scoreboard-quality-and-cost` — **[GAP]** no per-workflow
  scoreboard tracking quality/cost over time. ISSUE: #4344.
- `workflows.run.cost-tracking-per-node` — **[GAP]** no per-node/per-workflow
  spend visibility. ISSUE: #4343.
- `workflows.run.comparison-node` — **RESHAPED (creative-director ruling, 2026-09-18, same as
  `research.md`'s `research.compare-folds-into-chat`):** the RESULT side of this design is
  retired — there is no persisted comparison node, view or window; a comparison's result is two
  sibling artifacts shown in two Reader panes with a diff lens. The PRODUCING side survives: a
  "run with A and B" action (today's Compare Models node-popover action, `node-config.md` F13)
  over two prompts or two workflows. How much of #4328 (node design), #2526 (comparison as a
  sidebar-level capability) and #1339 (loove integration — loove itself stays a window, a
  diagnostic matrix) survives that reshaping is a creative-director triage, not decided here;
  the three issues stay open. → #4705 owns the pane-side replacement (its own not-yet-numbered
  increment).

### D. The workflow bar

- `workflows.bar.selection-projected-through-accepted-inputs` — **[OK]** which
  verbs the bar shows is a pure function of the current selection against each
  workflow's server-declared `accepted_inputs`, computed in `WorkflowBarPolicy`
  with no SwiftUI (`WorkflowBar.swift:8-12`). Pinned: `WorkflowBarPolicyTests`.
- `workflows.bar.click-appends-not-runs` — **[PARTIAL]** (implemented,
  unpinned; #4797) clicking a verb appends it to an in-progress chain; running
  is a separate, deliberate action (`WorkflowBar.swift:39-41`).
- `workflows.bar.folder-order-and-icons-served` — **[PARTIAL]** (implemented,
  unpinned; #4797) the bar's verb-group order and glyphs come from the server
  (`resources/workflow_folders.json`), not a client-side hard-coded list, so a
  server-added folder is orderable/iconable without an app release.
- `workflows.bar.labels-toggle-persists` — **[PARTIAL]** (implemented,
  unpinned; #4797) the bar's Show/Hide Labels choice writes back through
  `onSetLabels` rather than being a session-only UI toggle
  (`WorkflowBar.swift:33-36`).
- `workflows.bar.model-pin-per-step` — [OK] a step in the assembled chain can
  be pinned to a specific configured model (`modelChoices:
  [WorkflowBarModelChoice]`, `WorkflowBar.swift:26-27`). Pinned:
  `WorkflowBarModelPinTests`.

### E. Default/locked workflows and folders

- `workflows.defaults.locked-container-refuses-drops` — **[OK]** the Default
  Workflows container and its subfolders render locked/purple and refuse drops
  (`Models/SidebarItem.swift:215-258`, `Models/Document.swift:597-606`).
  Pinned: `DefaultWorkflowLockTests`.
- `workflows.defaults.folder-click-opens-custom-view` — **[BROKEN]** clicking a
  legacy preset folder can open the custom workflow view instead of the
  expected folder browse, and legacy preset folders can be stuck at the tree
  root with no lock applied. ISSUE: #4186.
- `workflows.defaults.duplication-regrown` — **[GAP]** the shipped preset set
  has regrown near-duplicate presets (e.g. multiple topologically-identical
  transcription presets; Catalogue exists in three shapes) — a pruning pass is
  design work, not a bug fix (2026-07-29 review F15). (#4738).
- `workflows.defaults.chains-not-persisted` — **[GAP]** workflow chains
  assembled interactively are in-memory only — lost on restart, and can leak
  across libraries/users. ISSUE: #3181.
- `workflows.defaults.scope-contract-undeclared` — **[GAP]** a workflow has no
  declared contract for its source kind, fan-out, or where its output attaches
  — needed so scope-widening bugs (the class the confirm/cancel gate patched
  point-fashion, `workflows.run.scope-widening-confirmed`) get closed
  structurally rather than one at a time. ISSUE: #4397.

### F. Folders of workflows (library/organization)

- `workflows.folders.route-ordered-not-alphabetical` — **[PARTIAL]**
  (implemented, unpinned; #4797) the server-declared folder order follows the
  actual processing route (image editing → … → export), not alphabetical or
  client-invented order (`workflow_folders.json:2`).
- `workflows.folders.unknown-folder-still-visible` — **[PARTIAL]** (implemented,
  unpinned; #4797) a folder absent from the served list sorts after the known
  route with a fallback glyph rather than being hidden (`workflow_folders.json:2`).
- `workflows.folders.empty-states-suggest-a-workflow` — **[GAP]** an empty
  state (e.g. a folder with nothing transcribed) does not yet offer the
  workflow that would fill it. ISSUE: #4387.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | `WorkflowSavePolicy.canAutoSave`, `WorkflowBarPolicy` selection projection, `WorkflowOutputLog` source-tool exclusion | `fichero/Tests/Unit/general/Views/Workflow/*Tests.swift` |
| Availability (Swift) | y | canvas/inspector/run-log reachable given a workflow selection | same, `AppSource.root()` |
| Backend (pytest) | y | `validate_port_connection`, `activity_store` run status/timeline, default-workflow seeding | `fichero-server/tests/unit/workflows/**` |
| MCP | n | workflows are not currently exposed as MCP tools beyond `fichero_workflow_*` wrappers — out of scope for this spec | — |
| CLI | y | `fichero workflow run`/`status`/`list` wire the same endpoints the UI uses | `fichero-cli/tests/test_workflow_*.py` |
| Click-around (XCUITest, Mac) | y | open a workflow, add/connect a node, run it, read the output log | `fichero/Tests/UI/general/<WorkflowFlow>UITests.swift` |
| iPhone (iOS) | n (canvas editing is Mac-only today; the bar/run log may reach iOS later) | — | — |
| iPad | n (same) | — | — |
| Load (#4634) | n | not yet scoped for this surface | — |

Pure-policy tests first: `WorkflowSavePolicy.canAutoSave` and `WorkflowBarPolicy`
are both already designed to be tested without a window (no SwiftUI in either) —
the highest-leverage, cheapest tests to land first, ahead of any XCUITest.

## Open questions for the creative director

1. **Should `workflow-node-config.md` fold wholesale into this spec, or stay a
   separate sub-spec it's cross-referenced from?** Recommendation: keep it
   separate for now (it's APPROVED and shipped; folding it in would force a
   Status downgrade or a split-status file) but give it its own
   `Milestone: workflow-node-config` so it stops being a milestone-orphan, and
   have this spec's milestone `workflows` be the umbrella the creative
   director tracks both under.
2. **Which of the two open "Workflow View" (#252, 24 open) and "Workflows"
   (29 open) milestones becomes the canonical `workflows` milestone this spec
   points at?** Recommendation: rename #252 to `workflows` (larger, more
   actively triaged) and re-target #… 's open issues onto it, closing the
   duplicate.
3. **Is the canvas edge-legality fix (engine-owned table, client consumes it)
   worth doing before or after the modes-to-panes canvas-relocation
   (increment 2)?** Recommendation: before — moving the canvas to a narrower
   Preview pane (per modes-to-panes) makes a wrong, silently-drawable edge even
   easier to create by accident in cramped space.
4. **Should the ~16 non-executable palette tools (#4312 area, review F11) be
   hidden from the palette immediately, or left visible with a "not yet
   runnable" affordance while they're built out?** Recommendation: hide
   immediately — a palette entry that fails at graph-build time is worse than
   an absent one; re-add as each tool ships a real `@register_tool`.
5. **Does `workflows.defaults.duplication-regrown` (near-duplicate presets)
   get its own issue now, or wait for the broader "Workflow verification
   program" (#4369) to surface it as one of its findings?** Recommendation:
   file it now as a small, scoped issue — pruning is cheap and #4369 is a
   large audit that may not land soon.
6. **Is `workflows.run.wrong-scope-runs-whole-folder` (#4396) actually closed
   by the `widensBeyondSelection` confirm/cancel flow already in
   `WorkflowEditor.swift:33-36`, or still reproducible?** This spec could not
   confirm live behavior this session (no running engine); needs a quick
   manual re-check before the behavior tag is trusted either way.

## Sources folded in

Per the manager's instruction to fold still-true design content from agent-work
files triaged `MERGE-INTO-SPEC → Workflows` in
`INVENTORY_mode_specs.md` §3/§5, and to list which are now superseded (files
are NOT deleted or moved — this is a report only):

- `agent-work/reviews/2026-08-02-node-editor-fabel-review.md` — **superseded**
  for its Finding 1 (edge-legality divergence) and Finding 2 (fabricated
  fallback ports), both carried into §A above as `[BROKEN]`/`[BROKEN-partial]`
  behaviors. Its Finding 3 (no tests assert canvas/engine agreement) is carried
  into this spec's Test matrix as the pure-policy-first recommendation.
- `agent-work/reviews/workflow-results-review.md` — **superseded** for its §2
  P0/P1 findings (F1–F11) folded into §C `workflows.run.*` behaviors above, and
  its §3 target-design sections (results surfacing, provenance-first artifact
  browser, per-step trace, activity model) which back the `[GAP]` tags and the
  #4312 EPIC cross-reference. Its §3.5 node-editor findings are folded into §A
  alongside the 2026-08-02 review. NOT superseded: its P2 findings F14–F20
  (artifact ordering, default-workflow duplication F15, AI-tier/preflight
  gaps F16, LangChain observability F17, sub-workflow DB-vs-JSON drift F18,
  stubbed E2E tests F19, activity-plumbing races F20) are evidence for this
  spec's `[GAP]`s but the review itself remains the fuller citation — kept in
  agent-work as the detailed record.
- `agent-work/reviews/workflow-issue-drafts.md` — **not superseded**: it is the
  issue-draft source for many of the ISSUE numbers cited above (#4312 and its
  siblings were filed from this document per its own commit trail); it remains
  the readable narrative behind those issue numbers and should stay in
  agent-work as backlog-drafting history, not be folded verbatim into this
  spec.
- `agent-work/design/text-workflows-report.md` — **partially folded**: its
  quality findings (programmatic cleaner destroying tally-page numbers,
  DeepL host/quota misdiagnosis, translation prompt trailing-space tune,
  Capture-OCR-and-Transcribe wrong-file bug) are all backend/tool-behavior
  fixes already committed (see its own "Commits" section) rather than open
  design gaps — NOT carried into this spec's Behaviors, since they are
  fixed-and-shipped tool internals, not surface design. Its "Open
  rulings / not fixed" section (library-scoped settings collide across
  concurrent runs; CLI short-id resolution for `workflow run`; economy-preset
  fresh-install refusal) feeds `workflows.defaults.scope-contract-undeclared`
  (#4397) and is worth a future pass, not carried as its own behavior id here
  to avoid inventing an id for content that is process-note-shaped, not
  surface-shaped.
- `agent-work/design/workflow-exercise-report.md` — **not folded**: read only
  for its section headers; it is the earlier (2026-09-02) sibling of
  `text-workflows-report.md` covering the same class of tool-execution defects
  (already fixed/committed per its own account) rather than surface design.
  Kept in agent-work as exercise-run history.
- `agent-work/superpowers/specs/2026-07-24-context-menu-run-workflow-targets-design.md`
  — **folded conceptually, not as a numbered behavior**: this document
  specifies "Run Workflow" from a Sidebar/Library context menu using a pure
  target resolver (clicked target vs. selection, folders contribute direct
  children only, no recursion). It reads as SHIPPED design intent for the
  workflow bar's selection-projection behavior family
  (`workflows.bar.selection-projected-through-accepted-inputs`) rather than a
  distinct gap; no code was checked this session to confirm the resolver
  exists as specified, so it is not tagged `[OK]` here — flagged for the
  `workflows.bar.*` section's next revision to verify and either promote to a
  numbered `[OK]` behavior or demote to `[GAP]`.

Not folded (per the inventory's own "not reviewed line-by-line" budget note):
`agent-work/design/manual-capability-reference.md`,
`agent-work/design/grand-sweep-report.md`,
`agent-work/design/view-unification-notes.md` — these came up in the original
broad grep as cross-cutting UI surveys, not Workflows-specific; worth a second
pass in a future revision of this spec, not read this session.

## Issue map (milestone `workflows` #293, redone 2026-09-18 after the truncated-fetch bug
was fixed — see `scripts/spec_pipeline.py`'s `GH_ISSUE_FETCH_LIMIT`)

Every OPEN issue on this milestone (56, the real count — the first pass under-counted at 29
because the fetch silently truncated at 1000 issues), mapped to the behavior it covers or
marked UNCOVERED. `nodeconfig.*` issues (milestone `workflow-node-config` #298, its own spec)
are out of scope for this table — see that spec's own behaviors, all already cited.

| Issue | Title | Behavior | Note |
|-------|-------|----------|------|
| #4186 | Default Workflows: legacy preset folders stuck at root, no locks, folder click opens custom view | `workflows.defaults.folder-click-opens-custom-view` | cited |
| #4312 | EPIC: Every run tells you what it did — provenance, trace, honest controls | `workflows.run.provenance-run-id-on-artifacts`, `.pause-is-dead-end`, `.stuck-processing-on-cancel-fail`, `.controls-are-fire-and-forget`, `.trace-view` | cited (5 behaviors) |
| #4340 | Canvas follow-ons: resize handles, trackpad pan, arrange commands | `workflows.canvas.arrange-and-resize` | cited |
| #4342 | Workflow version history: snapshots + visual diff | `workflows.canvas.version-history` | cited |
| #4343 | Cost tracking: per-node and per-workflow spend | `workflows.run.cost-tracking-per-node` | cited |
| #4344 | Per-workflow scoreboard: quality and cost tracked over time | `workflows.run.scoreboard-quality-and-cost` | cited |
| #4370 | Test / Dry Run button on a workflow | `workflows.canvas.dry-run` | cited |
| #4387 | Empty states should offer the workflow that fills them | `workflows.folders.empty-states-suggest-a-workflow` | cited |
| #4397 | Workflows need a declared scope contract | `workflows.defaults.scope-contract-undeclared` | cited |
| #4478 | Decide the six port conversions the old editor permitted | `workflows.canvas.edge-legality-matches-engine` | cited |
| #4736 | `workflows.canvas.ports-come-from-registry` — client fabricates fallback ports | `workflows.canvas.ports-come-from-registry` | cited |
| #4738 | `workflows.defaults.duplication-regrown` — near-duplicate default presets regrown | `workflows.defaults.duplication-regrown` | cited |
| #4746 | `workflows.canvas.16-palette-tools-cannot-execute` | `workflows.canvas.16-palette-tools-cannot-execute` | cited |
| #4797 | ui/workflows.md: 9 behaviors implemented but unpinned | `workflows.canvas.renders-nodes-edges-ports`, `.canvas.duplicate-to-edit`, `.run.output-log-live`, `.run.source-tools-excluded-from-file-columns`, `.bar.click-appends-not-runs`, `.bar.folder-order-and-icons-served`, `.bar.labels-toggle-persists`, `.folders.route-ordered-not-alphabetical`, `.folders.unknown-folder-still-visible` | cited (this pass's own bucket issue, 9 behaviors) |
| #1818 | Show workflow cost estimate up front | `workflows.canvas.cost-estimate-up-front` | cited |
| #2440 | Show the hidden tools (tool/node palette not showing all available tools) | `workflows.canvas.hidden-tools-in-palette` | cited |
| #2441 | Every workflow node must be an editable tool | `workflows.canvas.every-node-editable-tool` | cited |
| #2442 | Make workflow fan-out editable + understandable | `workflows.canvas.fan-out-editable` | cited |
| #2443 | Audit workflow node editor for parity with backend workflow capabilities | `workflows.canvas.ports-come-from-registry` | cited (umbrella; #4736 above is the precise fallback-port claim) |
| #3181 | Chains are in-memory only — lost on restart, leak across libraries/users | `workflows.defaults.chains-not-persisted` | cited |
| #4328 | Comparison node: document-aware ports, persisted results, current model defaults | `workflows.run.comparison-node` | **RESHAPED this pass — needs CD triage** — the result is panes + a diff lens now (CD ruling, 2026-09-18), never a node; the behavior line is retired, pointing at → #4705 |
| #2526 | Comparison is a sidebar-level capability, not buried in the workflow tool | (reshaped, see #4328) | **NEEDS CD TRIAGE** — the ruling itself compares two prompts OR two workflows, which is this issue's claim |
| #1339 | Comparison framework: integrate loove | (reshaped, see #4328) | **NEEDS CD TRIAGE** — same ruling; loove itself stays a window (diagnostic matrix), per the ruling |
| #3907 | Translation workflows: cross-check default; consolidate Translate/DeepL/Double-Check | — | **UNCOVERED** — cluster: transcription/translation presets |
| #3909 | Extraction / Catalogue workflows: verify / consistency pass | — | **UNCOVERED** — cluster: transcription/translation presets |
| #4306 | Translate from artifact context menu fails with an error | — | **UNCOVERED** — cluster: transcription/translation presets |
| #4633 | Transcribe fan-out: cloud provider 401 after several images | — | **UNCOVERED** — cluster: transcription/translation presets |
| #970 | OCR bounding boxes: persist per-text-region bbox, tie KG claims to them | — | **UNCOVERED** — cluster: bounding-box capture |
| #1659 | Align clean transcript ↔ Apple Vision bboxes → highlight entities on the page | — | **UNCOVERED** — cluster: bounding-box capture |
| #1834 | Capture line-level bounding boxes during transcription | — | **UNCOVERED** — cluster: bounding-box capture (near-duplicate of #970/#2104 — worth a triage pass on its own) |
| #2104 | Transcription (VLM / Apple Intelligence) must capture per-region bounding boxes | — | **UNCOVERED** — cluster: bounding-box capture (near-duplicate of #970/#1834) |
| #4309 | Capture text bounding boxes on first pass in all vision workflows | — | **UNCOVERED** — cluster: bounding-box capture |
| #754 | Analysis tool: Sentiment classifier | — | **UNCOVERED** — cluster: tool capabilities & registry |
| #1648 | Export a workflow as a portable LangGraph project | — | **UNCOVERED** — cluster: tool capabilities & registry |
| #1836 | [Apple] Upgrade fm-bridge to Foundation Models 2026 | — | **UNCOVERED** — cluster: tool capabilities & registry |
| #4310 | Audit unused langchain/langgraph capabilities | — | **UNCOVERED** — cluster: tool capabilities & registry |
| #4329 | Conversion workflows: export to HTML, SVG, Markdown | — | **UNCOVERED** — cluster: tool capabilities & registry |
| #4368 | Native Apple image ops via the bridge (replace OpenCV/model paths) | — | **UNCOVERED** — cluster: tool capabilities & registry |
| #4399 | EPIC: multi-level cataloguing — describe box/archive/folder/item | — | **UNCOVERED** — cluster: tool capabilities & registry |
| #1665 | Catalogue pauses after transcribe on imported pages, skips KG writer | — | **UNCOVERED** — cluster: Catalogue pipeline / KG-writer staging |
| #1668 | Workflow checkpoint reports artifacts/KG but fresh library persists zero rows | — | **UNCOVERED** — cluster: Catalogue pipeline / KG-writer staging |
| #1669 | Separate Catalogue workflow into artifact→entity extraction→merge→SVO/KG stages | — | **UNCOVERED** — cluster: Catalogue pipeline / KG-writer staging |
| #1676 | Split SVO/KVO claim generation into a persisted post-entity workflow stage | — | **UNCOVERED** — cluster: Catalogue pipeline / KG-writer staging |
| #3387 | Catalogue menu item does nothing and prior steps do not update document content | — | **UNCOVERED** — cluster: Catalogue pipeline / KG-writer staging |
| #115 | [QA] Workflow Editor Surface Audit | — | **UNCOVERED** — cluster: workflow data-model & verification |
| #3949 | Routed workflows fail validation after a DB round-trip | — | **UNCOVERED** — cluster: workflow data-model & verification |
| #4277 | Design: workflow recipes are user-level, runs are library-pinned | — | **UNCOVERED** — cluster: workflow data-model & verification |
| #4369 | Workflow verification program: every preset proven on both axes | — | **UNCOVERED** — cluster: workflow data-model & verification |
| #1660 | Workflow node editor: make each node clear about what it consumes + produces | — | **UNCOVERED**, below-threshold pair with #2524 — node-editor structural clarity (2 issues, not clustered) |
| #2524 | Workflow node editor: clickable/editable edges, editable fan-out, graph = actual execution | — | **UNCOVERED**, below-threshold pair with #1660 |
| #257 | Resolve remaining blockers on the coherent AI layer | — | **UNCOVERED** — too vague/broad to be workflows-specific; recommend the manager re-scope or re-home |
| #1594 | Real-data processing: Jesuit Mapping + Marshall Diaries — local CLI pipeline | — | **UNCOVERED** — a specific research project's data pipeline, not a general workflows behavior; recommend re-homing off this milestone |
| #2094 | EPIC: All models managed in Settings → Models | — | **UNCOVERED** — a Settings/Models surface epic, not workflows; recommend re-homing |
| #2591 | node-model: fold workspaces/tasks/issues/aliases/bookmarks/saved-searches into node types | — | **UNCOVERED** — the cross-cutting node-model EPIC (modes-to-panes/node-model territory); recommend re-homing, not a workflows sub-spec |
| #4330 | Rendition model and two-axis navigation in Preview | — | **UNCOVERED** — reads as `panes-workspaces`/Preview rendition work; recommend re-homing |
| #4339 | Library: Finder-style grouping (group-by in the sort menu) | — | **UNCOVERED** — a Library browsing feature; recommend re-homing |

**Coverage: 20 of 56 cited, 3 RESHAPED and awaiting CD triage (Comparison — the result side retired by the CD ruling), 33
UNCOVERED** (36 total orphan issues by `check`'s rule-f count, since the 3 reshaped issues
are now also uncited and correctly show up as orphans too — 20+3+33=56, 33+3=36 rule-f
lines). Clustered by theme (creative-director instruction: propose a sub-spec only for a
cluster with ≥4 issues; PROPOSAL ONLY, not written, no milestone created):

- **Transcription/translation presets** (#3907, #3909, #4306, #4633 — 4 issues): quality and
  reliability of the shipped preset workflows themselves (cross-check defaults, verify/
  consistency passes, fan-out key propagation, context-menu translate). **Proposed sub-spec:
  `workflows-transcription-presets`** — intent: "each shipped preset workflow (Transcribe,
  Translate, Extract, Catalogue) behaves correctly and consistently under its own declared
  contract, including parallel/fan-out execution." Issue list: #3907, #3909, #4306, #4633.
- **Bounding-box capture** (#970, #1659, #1834, #2104, #4309 — 5 issues, at least two of
  which read as duplicates of each other): per-region/line-level bounding boxes captured
  during transcription and tied to KG claims. **Proposed sub-spec:
  `workflows-bounding-box-capture`** — intent: "every vision workflow persists the bounding
  box it read a value from, at the granularity (region/line/word) the tool actually reports,
  and KG claims carry that anchor." First step before writing it: triage #970/#1834/#2104
  for exact duplication. Issue list: #970, #1659, #1834, #2104, #4309.
- **Tool capabilities & registry** (#754, #1648, #1836, #4310, #4329, #4368, #4399 — 7
  issues): what tools exist and where their capabilities come from (native Apple ops
  replacing OpenCV, conversion formats, cataloguing, a sentiment-classifier tool, exporting a
  workflow as a portable LangGraph project, an fm-bridge upgrade, an audit of unused
  langchain/langgraph capacity). **Proposed sub-spec: `workflows-tool-capabilities`** —
  intent: "the tool catalogue's capabilities are declared, audited, and exploited (no unused
  engine capacity, no missing conversions), independent of the canvas/run/bar UI this spec
  already covers." Issue list: #754, #1648, #1836, #4310, #4329, #4368, #4399.
- **Catalogue pipeline / KG-writer staging** (#1665, #1668, #1669, #1676, #3387 — 5 issues):
  the Catalogue workflow's multi-stage pipeline (artifact → entity extraction → merge →
  SVO/KG) drops rows, pauses, and doesn't persist a checkpoint's claimed writes. **Proposed
  sub-spec: `workflows-catalogue-pipeline`** — intent: "Catalogue's stages are separated,
  each stage's output is verified persisted before the next runs, and a stall/failure is
  visible rather than silent." Issue list: #1665, #1668, #1669, #1676, #3387.
- **Workflow data model & verification** (#115, #3949, #4277, #4369 — 4 issues): a
  recipe/run ownership design doc, a DB round-trip validation bug, a QA surface audit, and a
  cross-preset verification program — all about whether the workflow OBJECT MODEL has a
  declared, verified contract. **Proposed sub-spec: `workflows-data-model-verification`** —
  intent: "a workflow's recipe/run/scope contract is declared once and verified end-to-end
  (DB round-trip, QA audit, cross-preset check), not assumed." Issue list: #115, #3949,
  #4277, #4369.
- **Below threshold, not proposed** (#1660, #2524 — 2 issues): workflow node-editor
  structural clarity (what a node consumes/produces, editable edges/fan-out). Recommend
  folding into whichever of the clusters above ends up owning canvas/node-editor scope, once
  one exists.
- **Recommend re-homing off this milestone entirely** (#257, #1594, #2094, #2591, #4330,
  #4339 — 6 issues): too vague to be workflows-specific (#257), a specific research project's
  data pipeline rather than a general behavior (#1594), a Settings/Models epic (#2094), the
  cross-cutting node-model EPIC that belongs to modes-to-panes/node-model territory (#2591),
  Preview rendition work that reads as `panes-workspaces`' surface (#4330), and a Library
  browsing feature (#4339). None of these six are workflows-canvas/run/bar/defaults/folders
  behaviors as this spec defines them.
