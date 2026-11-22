# Research — Design Spec (#2067)

> Milestone: research
> Manual: TBD — a Getting Started section explaining that Research is the app's one
> agentic surface: a chat below the sidebar is where you talk to your project, a research
> folder keeps one line of research (its chats, notes, sources and staged imports), and the
> Plan pane shows that folder's leads, searches and sources, and what the agent did.

> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code
> makes them pass. **Status: DRAFT — awaiting approval before tests/code.**
>
> THREE ANCHORS: milestone `research` (this doc), manual TBD above, tests cited in the Test
> matrix. Tags: **[OK]** built · **[GAP]** intended, never built (needs an issue) ·
> **[PARTIAL]** exists elsewhere / not fully wired · **[BROKEN]** regression, code
> contradicts the ruling (needs an issue) · **[PROPOSED]** decided here, not yet built.
>
> Placement/rendition (dock vs. pane, kind-switcher) is owned by `modes-to-panes.md` — this
> spec cross-references its `m2p.*` behaviors rather than restating the matrix.
> Sidebar-node/pane mechanics generally are owned by `panes-workspaces.md`.

## Ruled 2026-11-21 (owner; paraphrased): Research to the new UX

Much of Research, chat and the agent is built; its chrome predates the new UX (one pane menu, tools in
islands, one title, Finder selection). The owner first leaned to a window of its own and then ruled, the same
day, the following. Sections F to J under Behaviors and the Build order carry it; where older text below
disagrees, this ruling wins.

1. **Research is not a separate window.** It lives in the main window as it does now: the chat sits below
   the sidebar tree, and a line of research is a node in that tree with its content in the main window's panes.
2. **Its runs are Activity jobs.** Research draws no run list of its own; a run is watched, paused and stopped
   in Activity (`ui/activity-pane.md`).
3. **Its models come from the Models system.** No picker belongs to Research or to chat; the model is chosen
   in the Models and Compute window (`ui/models-and-compute-window.md`).
4. **The project-management side** (the brief, the leads and their milestones, the search log, the source
   register, the staged imports, what the agent did) **is a pane of the main window with an optional window of
   its own, as Activity is.** It is the only part of Research that may have a window.
5. **One word, one meaning.** "Workspace" had four meanings (section I). In what a person reads it now means
   only a window's saved pane layout; the thing that holds a line of research is a **research folder**.

Owner answers, 2026-11-21, to the questions the review raised:

6. **The names stay:** "Research folder" and "Plan". There is ONE Plan window, with a source list of research
   folders.
7. **Accepted staged imports land in that research folder.**
8. **Checklists fold into Plan leads and tasks,** converted when a research folder is opened.
9. **The embedded browser is brought to the new UX in Stage 1,** not deferred (Step 1.5).
10. **Library text goes to a cloud model only where that library allows it:** a per-library setting, cloud
    allowed or local only.
11. **A catalogue that needs a login, or blocks scripts, turns its lead into "requested" for the owner,** with
    its terms ready.
12. **The agent has an editor account on one pilot library only.** Every staged import waits for the owner's
    Accept.

**A research folder, in one sentence:** a research folder is an ordinary folder in the project's tree, marked
as research, that holds one line of research (its chats, notes, search log, source register and staged
imports), while a workspace is only a window's saved pane layout.

## Superseded rulings

- **Chat's five tabs, the Research sidebar mode and "research workspace" as a name (owner, 2026-11-21).** The
  text below that describes Conversation · Sources · Plan · Knowledge · Compare as chat's tabs, a Research
  mode with a project list beside a three-pane view, a model picker in chat's bar, and "Save as Workspace" is
  what is BUILT, kept as the record. What should be is sections F to J. Read "research workspace" below as
  "research folder".

- **Chat placement is free-form, not fixed zones (creative director, 2026-09-18).** An
  earlier ruling (2026-07-20, captured in
  `agent-work/design/agentic-surface-consolidation-fabel-review.md`) described chat as
  confined to three fixed docking zones. That is **superseded**: chat is a movable pane
  like any other kind, and sitting below the sidebar is only its DEFAULT placement. The
  mechanics of making chat movable (lifting conversation state out of `ChatView`'s `@State`
  so there is never a double mount) belong to `modes-to-panes.md` increment 6 — see that
  spec, not restated here.

## Intent (the design)

There is **one** agentic surface in Fichero, named **Research** — the activity, not a
persona. The AI is an instrument the user directs, not an interlocutor with a
pretend-human name (`docs/contributor_manual/architecture/agent_chat_as_user.md`; the
2026-07-19/20 creative-director rulings captured in
`agent-work/design/agentic-surface-consolidation-fabel-review.md`). "Chat", "Researcher",
"Agent", and "Workspace" are not separate features — they are one continuum from a
lightweight chat bubble to a full research workspace, and every mutation the agent makes
flows through the same audited action layer a human user's clicks use
(`fichero-server/src/fichero_server/actions/registry.py:156-210`).

Concretely, the user should be able to observe:

- A **plain chat** — `ChatView` (`fichero/fichero/Views/Chat/ChatView.swift`) — docked
  below the sidebar tree by default, but free-form movable to any pane like any other kind
  (owned by `modes-to-panes.md`/`panes-workspaces.md`), grounded on whatever is
  selected/visible.
- A chat is kept by filing it into a **research folder** (File › Keep in Research Folder…, section I). Today
  the door is the chat's Plan tab, which with no project shows an invitation ("Save this chat as a workspace
  to plan tasks, track sources, and keep notes", `ChatView.swift:245-258`); that tab and its wording go
  (`research.ux.chat-has-two-views`, `research.words.workspace-means-a-layout`). The continuum is one seam,
  not two products.
- A **research folder** (called a research workspace until 2026-11-21) that is a folder node in the library tree, not a bespoke
  document type: `DocumentStore.createWorkspace(name:)` literally creates a folder and
  marks it (`fichero/fichero/Models/DocumentStore+CRUD.swift:43-48`,
  `documentService.markAsWorkspace(folderId:)`). Chats, notes, tasks, checklists, sources,
  and saved outputs live as child nodes of that folder; library items the workspace draws
  on enter by **alias** (`Document.aliasTargetId`, `Document.swift:297-298`; engine
  `node_aliases.py`) — never moved out of where the user filed them.

## Prior art / best practices

- **Agentic-tool calling as an OpenAI/LiteLLM tool-call loop** (function calling over a
  bounded turn budget) is the established shape for "chat that acts" — Fichero's
  `action_tools()`/`dispatch_tool_call()` (`fichero-server/src/fichero_server/actions/chat_tools.py`)
  and `_run_chat_tools_loop` (`fichero-server/src/fichero_server/api/routes/system/chat.py:594`)
  follow it rather than inventing a bespoke agent protocol.
- **Model-as-account, not model-as-superuser** follows the same RBAC/audit pattern web apps
  use for service accounts: a real identity, a real role, a real audit row
  (`agent_chat_as_user.md`). Fichero reuses its EXISTING `AccountUser`/`LibraryRole`/
  `ActionAudit` tables rather than a parallel "AI audit" system.
  Fichero deliberately does **not** adopt a separate agent-memory/vector-store product for
  research notes/plans — its research state (`ResearchProject`/`ResearchPlan`/
  `ResearchTask`) is ordinary rows plus library documents, so it stays queryable through the
  same KG/search the rest of the app uses instead of a second, siloed index.
- **A working folder for agent output** mirrors how coding agents (and Zettelkasten-style
  research tools) scope a session's writes to one directory rather than the whole
  filesystem — here the folder is a library node, and its trust boundary is explicit: the
  embedded browser pane has free internet egress but its ONLY crossing point into the
  library is `POST /api/research/tools/browser-save`
  (`fichero/fichero/Views/Chat/Research/ResearchBrowserPane.swift:6-13`).

## The continuum (chat ↔ research)

| | Plain chat | Research workspace |
|---|---|---|
| Identity | `Conversation`, ephemeral until saved | A folder node (`workspace_kind=agent`), permanent |
| Where it lives | Sidebar dock or a pane (owned by `modes-to-panes.md`) | Sidebar node, like a workflow (`m2p.research-is-sidebar-node`) |
| Context | Whatever is selected/visible — the implicit "eye" scope (`ChatViewToolbar.swift:70-83`) plus pinned documents | The workspace's own working folder: child chats/notes/outputs, plus aliased library items |
| Promotion in | — | `ChatView.saveAsWorkspace()` (`ChatView.swift:239-245`) — same conversation, same messages, now with a Plan |
| Surface | `ChatView` tabs: Conversation · Sources · Plan · Knowledge · Compare | Same tabs; Plan now renders `ResearchTasksPane` (Tasks/Checklists/Sources/Notes) instead of the invitation |

There is no separate "Researcher mode" and no separate "Agent" persona — a research
workspace is what a chat becomes when its Plan tab has a project behind it. The old
3-pane `ResearchWorkspaceView` (CHAT | BROWSER | TASKS,
`fichero/fichero/Views/Chat/Research/ResearchWorkspaceView.swift`) and the standalone
`ResearchProjectListView` sidebar-mode list predate this ruling and are folded in below —
their capabilities (embedded browser, task/checklist/source/note panes) survive as
Inspector content, not as a rival top-level surface.

## What exists today (grounded)

### Chat surface

- `ChatView` (`fichero/fichero/Views/Chat/ChatView.swift:45`) is a RAG chat view with five
  tabs on `ChatSurfaceTab` (`ChatView.swift:7-38`): **Conversation**, **Sources**, **Plan**,
  **Knowledge**, **Compare** — rendered through the shared `SurfaceTabBar`
  (`fichero/fichero/Views/Shell/SurfaceTabBar.swift:33`, doc comment names Reader/Inspector/
  Workflow/Chat/Research/Search as the protocol's adopters).
  - **Correctness risk:** `currentConversation` and `backendConversationId` are `@State`
    on `ChatView` (`ChatView.swift:66,70`) rather than lifted into a per-window model.
    `modes-to-panes.md`'s `m2p.chat-single-mount` names the consequence directly: a second
    mount of `ChatView` for the same conversation double-sends, because each mount owns
    its own copy of that state. This spec does not re-solve it — it is
    `modes-to-panes.md`'s to fix before chat becomes freely placeable.
  - **Sources tab IS "Chat Scope".** `sourcesTabContent` (`ChatView.swift:186-207`) mounts
    `ChatInspector` inline (`ChatInspector.swift:7`) bound to the same `selectedDocuments`
    the composer's pin menu and drop targets write to, plus a read-only "cited" ledger
    below it (`SourceLedgerEntry.ledger(for:)`). `modes-to-panes.md`'s
    `m2p.chat-scope-inspector-only` flags this as a **[BROKEN]** duplicate: the SAME
    `ChatInspector` is also reachable from the composer's paperclip sheet
    (`ChatView.swift:335-352`), so two call sites mount it instead of one. This spec's
    ownership of "what the Sources tab means" is Chat Scope = pinned + implicit + cited
    documents; the single-mount fix is `modes-to-panes.md`'s.
  - **Plan tab is the continuum seam.** With `researchProject` present it renders
    `ResearchTasksPane(project:)`; with none, an invitation to `saveAsWorkspace()`
    (`ChatView.swift:210-231`).
  - **Compare tab — SUPERSEDED (creative-director ruling, 2026-09-18).** This tab used to
    reuse `ModelComparisonView()` verbatim (`ChatView.swift:241`); that design is retired.
    Comparison is now panes + a diff lens, not a chat surface: a "run with A and B" action
    leaves two sibling artifacts, and the Compare workspace shows them in two Reader panes
    with a diff lens — no Comparison view, node, or window, and chat's Compare tab is not
    its home either. See `research.compare-folds-into-chat` below. → #4705 (the pane-side
    design + `ComparisonDetailView`/`AppViewMode.comparison` deletion is its own increment,
    not yet numbered — three live sidebar sites still construct `.comparison`).
  - **Knowledge tab** surfaces entity/claim reference COUNTS from
    `ConversationKnowledgeSummary`, honestly labeled as not yet a browsable list
    (`ChatView.swift:255-259`) — the engine does not return entity/claim identities on a
    reply yet.
  - `ChatViewToolbar` (`fichero/fichero/Views/Chat/ChatViewToolbar.swift:10`) shows the
    conversation-history menu, the implicit-scope + pinned-document indicator, and
    `ChatModelPicker` — a shared popover reused across chat/island/settings/comparison
    (`ChatViewToolbar.swift:182-190`).
- **The chat dock.** `ContentView+SidebarLayout.swift:31-113` mounts `ChatView` BELOW the
  sidebar tree, gated on `showChatPane`, re-injecting the library's services across the
  column boundary (`ContentView+SidebarLayout.swift:60-70`, the #4513 rule). This is the
  ONE placement this spec assumes today; where else chat may render (a pane, a strip) is
  `modes-to-panes.md`'s matrix, not restated here.

### Research workspace

- `ResearchWorkspaceView` (`fichero/fichero/Views/Chat/Research/ResearchWorkspaceView.swift:4`)
  is a 3-pane CHAT | BROWSER | TASKS layout, predating the sidebar-node ruling — per
  `modes-to-panes.md`'s matrix row for research, it is a **[PROPOSED]**-to-retire bespoke
  container; the Library pane must never mount it (`m2p.library-is-always-navigator`'s
  shrinking allowlist already names `ResearchWorkspaceView(`).
- `ResearchProjectListView` (`fichero/fichero/Views/Chat/Research/ResearchProjectListView.swift:3`)
  is the older sidebar-mode list of research projects + workspaces (a separate
  `List`/`workspacesSection`), superseded by `m2p.research-is-sidebar-node`: research
  projects belong in the SAME sidebar tree as workflows, not a bespoke second list.
- `ResearchTasksPane` (`fichero/fichero/Views/Chat/Research/ResearchTasksPane.swift:3`) is
  the surviving unit — a segmented Tasks/Checklists/Sources/Notes picker over a
  `ResearchProject` — and is what the Plan tab already mounts (`ChatView.swift:222`). This
  is the shape the Inspector's Plan tab keeps.
- `ResearchBrowserPane` (`fichero/fichero/Views/Chat/Research/ResearchBrowserPane.swift:17`)
  is an embedded `WKWebView` with one audited crossing point into the library,
  `POST /api/research/tools/browser-save` — the module's own trust-boundary comment
  (`ResearchBrowserPane.swift:6-13`) is the strongest existing statement of "the agent's
  working folder stays isolated from open internet egress except through one audited
  save action". Its home surface is DECIDED (creative-director ruling, 2026-09-18, third
  round, `modes-to-panes.md` Rulings): it lives INSIDE the Source/Preview pane as
  `PaneSurface.webBrowser` — no browser pane kind, no tab strip of its own — not an
  Inspector tab. Design decided, not yet built; see `modes-to-panes.md`'s
  `m2p.browser-is-a-source-rendition` (→ #4809).
- `ResearchModels.swift` (`fichero/fichero/Models/ResearchModels.swift`) mirrors the
  backend's `research_models.py`: `ResearchProject` → `ResearchPlan` → `ResearchTask` /
  `ResearchNote` / `ResearchSource` / `ResearchChecklist`, plus `ResearchStep` (an
  executable search action: `web_search` / `browser_navigate` / `document_fetch` /
  `local_search`, `ResearchModels.swift:225-239`) — the "plan" a project's AI-authored
  research brief decodes leniently field-by-field (`ResearchPlanBrief.init(from:)`,
  `ResearchModels.swift:90-98`) so a model-shaped-differently plan degrades to partial
  display, never a decode failure.
- A workspace IS a folder: `DocumentStore.createWorkspace(name:)` creates an ordinary
  folder then calls `documentService.markAsWorkspace(folderId:)`
  (`fichero/fichero/Models/DocumentStore+CRUD.swift:43-48`) — the "research workspace is a
  folder node" ruling is not aspirational, it is how workspace creation is already
  implemented.

### The audited action layer

- `POST /api/chat`'s chat-tools loop is **DEFAULT ON** today (corrects the older
  `agent_chat_as_user.md` "not yet wired" claim — verified current in
  `fichero-server/src/fichero_server/api/routes/system/chat.py:561-588`): the agent gets
  read parity (every `read_only=True` registered action) plus a small explicit write
  allowlist, `CHAT_WRITE_ALLOWLIST = {workflow.run, entity.create, entity.update,
  claim.create}` (`fichero-server/src/fichero_server/actions/chat_tools.py:70-77`); every
  other mutation is refused and recorded, never invoked. `FICHERO_CHAT_TOOLS=0` is the kill
  switch back to single-shot RAG.
- Every dispatched tool call routes through `ActionRegistry.invoke(...)`
  (`fichero-server/src/fichero_server/actions/registry.py:156-210`): typed-param
  validation, authz write checks, the domain action, an `ActionAudit` row, and a change
  event — the SAME choke point a human user's UI click uses. `ActionContext.actor`
  (`registry.py:39-52`) is what makes "the model is a user" a literal attribution, not a
  slogan.
- Per-model tool grants (an owner choosing which tools a given model identity may call,
  beyond role) do **not** exist yet (`agent_chat_as_user.md` "Per-model tool grants… TO
  BUILD"); role (`viewer`/`editor`/`owner`) is the only authority boundary today.

## Behaviors

- `research.one-surface-named-research` — **[PARTIAL]** (implemented, unpinned; #4798) the
  surface is named Research; there is no separate "Researcher"/"Agent"/"Assistant" persona
  anywhere in the shipped UI (the `ChatSurfaceTab` doc comment states `chat = agent =
  workspace`, `ChatView.swift:5-6`). Kept open as the origin audit for this ruling: → #2571
  ("consolidate Researcher / Agent / Search surfaces… likely 3 endpoints → 1 model") first
  raised the question this behavior now answers on the UI side; Search staying a distinct
  retrieval primitive rather than folding into Research/chat is not itself decided here.
- `research.chat-is-lightweight-end` — **[PARTIAL]** (implemented, unpinned; #4798) a plain
  `ChatView` with no `researchProject` works standalone; the Plan tab's invitation is the
  only place the workspace concept surfaces (`ChatView.swift:210-231`).
- `research.plan-promotes-to-workspace` — **[PARTIAL]** (implemented, unpinned; #4798)
  `saveAsWorkspace()` persists the current conversation as a workspace on demand
  (`ChatView.swift:239-245`), the one continuum seam.
- `research.workspace-is-folder-node` — **[OK]** `createWorkspace` marks an ordinary folder
  (`DocumentStore+CRUD.swift:43-48`); library items enter by alias
  (`Document.aliasTargetId`), never moved. Pinned: `SidebarWorkspaceNodeTests`.
- `research.workspace-curated-items-crud` — **[OK]** (#1490; `fichero-server/tests/unit/api/test_routes_documents_workspace.py::test_workspace_patch_add_remove_reorder_items`, `::test_workspace_items_resolve_document_alias_targets`; checked 2026-11-21, the same routes `panes.workspace.crud-contract` cites: the two specs disagreed, this one said not built) a typed CRUD contract for a
  workspace's `curated_items` — add/remove/reorder aliased items atomically
  (`PATCH /api/documents/{id}/workspace`), a documented item schema (`{id, target_type,
  target_id, role, added_at, x, y, notes}`), and a resolve-to-full-objects read
  (`GET /api/documents/{id}/workspace/items`). Filed under a legacy milestone whose own name
  ("Workspace CRUD") collided with `panes-workspaces.md`'s unrelated "saved pane-layout"
  workspace concept — corrected here: `Document.is_workspace`/`curated_items` are THIS spec's
  workspace (the research folder node above), not a pane layout, so this belongs here, not
  there. Backend-only ask; not independently re-traced against `fichero-server/` this pass (a
  concurrent engine lane is mid-task there) — cited at face value from the issue's own claim
  that the fields already exist (`models.py:209`) and only the CRUD surface is missing.
- `research.sources-tab-is-chat-scope` — **[PARTIAL]** (implemented, unpinned; #4798)
  **updated for creative-director ruling 2026-09-18, point 3:** chat scope lives in BOTH the
  Inspector's Sources tab AND the chat dock's own Sources view — this supersedes an earlier
  review recommendation to collapse to "Inspector only." Today's code has `ChatInspector`
  plus the cited ledger (`ChatView.swift:186-207`) as the one built surface; a genuinely
  separate chat-dock Sources view (distinct from the Inspector mount) is not yet built.
  `modes-to-panes.md`'s `m2p.chat-scope-inspector-only` still names the two `ChatInspector`
  mount call sites (tab content + attach sheet) a duplicate BUG to collapse to one — that
  needs re-reading against this newer "both places" ruling before its fix lands, since
  collapsing to Inspector-only would now be the wrong direction.
- `research.project-is-sidebar-node` — **[GAP]** a line of research is a node of the sidebar tree
  (`modes-to-panes.md`'s `m2p.research-is-sidebar-node`), not the bespoke
  `ResearchProjectListView` sidebar-mode list that exists today. Tracked by → #4705 (the
  modes→panes EPIC) and #2446/#1738 (retire the Research sidebar mode into node kinds).
  Ruled 2026-11-21: the node IS the research folder (`research.folder.one-record`), so no second
  node kind, no `research:` row bucket and no `AppViewMode.research(…)` case are needed; the mode,
  its list and its View menu entry are deleted (`research.lives-in-the-main-window`).
- `research.plan-tab-is-only-plan-surface` — **[GAP]** `ResearchWorkspaceView`'s standalone
  3-pane container should retire once the Plan tab (`ResearchTasksPane`) and a Compare-tab
  browser rendition (open question below) cover its panes; today both the old container and
  the new tab exist side by side. No dedicated issue found for the `ResearchWorkspaceView`
  retirement specifically — (#4719) (distinct from → #4705's Library-pane-mount rule,
  which covers only where it must never mount, not its retirement).
- `research.chat-single-mount` — **[PARTIAL]** (→ #4705 increment 6) owned by `modes-to-panes.md`'s
  `m2p.chat-single-mount`; listed here because it blocks a workspace's chat from being
  freely placeable. Not re-specified.
- `research.chat-scope-single-mount` — **[BROKEN]** `ChatInspector` mounts from two call
  sites (`ChatView.swift:196` tab content and `ChatView.swift:340` attach sheet); owned by
  `modes-to-panes.md`'s `m2p.chat-scope-inspector-only`. Tracked by → #4705.
- `research.agent-audited-tools` — **[PARTIAL]** (implemented, unpinned; #4798) the
  chat-tools loop is default-on, read-parity + allowlisted-write, every call routed through
  `ActionRegistry.invoke` (`chat.py:561-588`, `chat_tools.py:70-93`, `registry.py:156-210`).
  The Fabel review that traced this subsystem end-to-end and filed most of this spec's other
  tracked issues (→ #4705, #4719, #4721, #4723, #4798, → #4809, → #4810, → #4811) is → #3310 — kept
  open as the tracking issue for its own remaining P1/P2 findings not yet individually filed
  (web-capture writes bypassing the audited action layer; the SSRF-duplicate response-size
  cap; missing DELETE routes for plans/tasks/steps/notes/sources/checklists; `ResearchStore`
  swallowing errors via `try?`; sources/checklists misemitting `note.*` events instead of
  `research.*`; client-supplied actor attribution on research rows). Also kept open here:
  #4431 (audited + invertible research tools recovered from an orphaned worktree, `ca2587a52`
  — the audited-action pattern applied to the research tool surface specifically) and #2280
  ("agentic chat as a first-class control surface" — one action registry, three entry points:
  MCP, App Intents/Siri, in-app chat, plus "chat builds workflows"). The MCP entry point is
  real (chat-tools shares the action registry MCP already exposes); the App Intents/Siri entry
  point and "chat builds workflows" are not verified built — narrower open scope than #2280's
  original framing. **Updated 2026-09-19, evidence from this week**: the MCP entry point's own
  write/delete tools were, until this week, the LEAST audited path in the system — the three
  MCP entity/claim write tools built their rows inline, bypassing `ActionRegistry.invoke`
  entirely (no `ActionAudit`, no undo, none of the action side's validation), and the two MCP
  delete tools did a bare `db.delete` with no `MutationLog`/`ActionAudit` either (fixed
  93b2e97e5, 54a13ffdf — each tool is now a thin caller of the same `entity.create`/`.update`/
  `.delete`/`claim.create`/`.delete` actions the UI and chat-tools loop use, with the request's
  real identity as actor). This closes a real gap between "the model is a user" as a slogan and
  as a literal, audited fact for the MCP surface specifically. **Explicitly unchanged by this
  fix, and the maintainer's own call to make**: neither `entity.delete` nor `claim.delete` is on
  `CHAT_WRITE_ALLOWLIST` (`chat_tools.py:70-77`, re-verified at HEAD) — the in-app chat agent
  still cannot delete anything; only the MCP path (a different caller, already privileged) can.
- `research.chat-context-aware` — **[PARTIAL]** (implemented, unpinned; #4798) the toolbar's
  implicit-scope indicator (`ChatViewToolbar.swift:70-83`) shows what the chat is grounded on
  by default; the composer's pin menu (`ChatView.swift:296-330`) layers explicit pinned
  documents on top. #1828 ("enable chat + query the unified index" — RAG + KG graph + full-text
  + ontology + hermeneutic layers, hybrid retrieval with grounded citations) asked for exactly
  this and looks substantially done — `ChatView` is already a RAG chat view per "What exists
  today" above — commented on the issue with this evidence and listed as verify-close rather
  than closed here.
- `research.per-model-tool-grants` — **[GAP]** no settings pane exists for an owner to grant
  or deny individual tools per model identity; role is the only boundary. Tracked by #2887
  (pluggable agent harness, scoped tools) — no issue found specifically for a per-model
  grant/deny UI — (#4721).
- `research.browser-pane-trust-boundary` — **[PARTIAL]** (implemented, unpinned; #4798)
  `ResearchBrowserPane`'s only library crossing is the audited `browser-save` action; no
  library/KG read tool is exposed to the embedded WebView (`ResearchBrowserPane.swift:6-13`).
- `research.embedded-browser-home-surface` — **[GAP]** (#4798) **ANSWERED (creative-director ruling,
  2026-09-18, third round, recorded in `modes-to-panes.md`'s Rulings): the embedded
  browser lives INSIDE the Source/Preview pane, no browser pane kind, no tab strip of its
  own.** This behavior id retires in favor of `modes-to-panes.md`'s three:
  `m2p.browser-is-a-source-rendition` (→ #4809, the placement itself),
  `m2p.scratch-browsing-persists-nothing` (→ #4810, scratch navigation persists nothing),
  `m2p.saving-a-source-makes-a-node` (→ #4811, only an explicit save makes a node). Not
  re-specified here; this spec still owns the trust-boundary and audited-save framing
  above. #2886/#4043 (needs-design, embedded-browser predecessors) are superseded by the
  now-decided design. **Still genuinely open, not decided:** the ruling is about PAGES —
  scratch browsing persists no pages/nodes — but whether cookies/logins (session state
  needed to keep reading a site across visits) are ALSO scratch, or persist separately, is
  not decided; pages being scratch is not the same claim as logins being scratch. See
  `modes-to-panes.md`'s `m2p.scratch-browsing-persists-nothing` note and #4810 for the
  options.
- `research.compare-folds-into-chat` — **[GAP]** (#4798) **SUPERSEDED (creative-director ruling, 2026-09-18):**
  this behavior described chat's Compare tab reusing `ModelComparisonView()` as Comparison's
  home. That design is retired: Comparison is now panes + a diff lens (a "run with A and B"
  action leaves two sibling artifacts shown in two Reader panes), never a chat tab, node, or
  window. Superseded by → #4705 (modes-to-panes owns the pane-side design and the
  `ComparisonDetailView`/`AppViewMode.comparison` deletion — its own increment, not yet
  numbered; three live sidebar sites still construct `.comparison`). Not re-specified here.
- `research.knowledge-tab-not-browsable` — **[PARTIAL]** shows honest reference counts, not
  a browsable entity/claim list, because the engine does not return identities on a chat
  reply yet (`ChatView.swift:246-260`). No dedicated issue found — (#4723).
- `research.manager-with-workers-orchestration` — **[GAP]** #2067, this spec's own origin
  EPIC ("ONE surface — Researcher + RAG/Graph chat + Agent converge; manager-with-workers in
  the sidebar"), describes a fuller orchestration runtime than what "What exists today" above
  documents: a **manager agent** that decomposes a request and dispatches **worker**
  sub-agents (#2069, `needs-design`), an **agent workspace** of sessions/tasks/milestones/
  issues/scratchpad the agent reads and writes as it reasons (#2072), those tasks/milestones
  **surfaced in the UI** (#2070), and **live visibility** into running sessions/subagents/
  parallel workflows/plan/thinking so the agent is never a black box (#2073). None of this is
  built — today's chat-tools loop is a single-agent tool-call loop, not manager-with-workers.
  Also tracked here: #247 (promote Chat to release once its acceptance gate is satisfied) — a
  release-readiness tracker for the surface this whole spec describes, not a design question.
- `research.canvas-actions-are-agent-tools` — **[GAP]** (#3093, redirected from the legacy
  "Library View - Spatial" milestone while folding `library-view-modes.md`'s pass 2) the five
  `canvas.*` audited registry actions (`canvas.layout.save`, `canvas.arrange`,
  `canvas.item.create/update/delete`) should be exposed through the chat-tools/MCP surface the
  same way `entity.create`/`claim.create` already are, with read tools so an agent can see a
  canvas before arranging it. Verified at HEAD: `CHAT_WRITE_ALLOWLIST`
  (`chat_tools.py:70-77`) does not include any `canvas.*` action — not built. This is the
  Library's Canvas/Space view modes becoming agent-operable, not a Research-surface behavior
  in its own right; it lives here because the audited-tool-exposure pattern is this spec's.

### MCP surface (legacy milestones "Agent View - Researcher", "Client - MCP")

- `research.mcp-servers-configurable-in-app` — **[PARTIAL]** (#509) contrary to the issue's
  own "Wire" framing, this is substantially built: `MCPServersView.swift`,
  `MCPServerDetailView.swift`, `AddMCPServerSheet.swift` mount a real add/browse/configure
  surface (cited already as built in `ai-settings.md`'s own fold, `SettingsTab.mcp` →
  `MCPServersView()`). Not independently re-verified this pass: whether "run a Fichero MCP
  tool directly" from the catalog (the issue's own pass-criteria checklist item) is reachable
  from this UI, or only server configuration is.
  Verified 2026-10-17: add/edit/delete and a server's tool list work end to end; `MCPToolsCatalogView` is mounted nowhere; no door runs one tool; the stdio allowlist refuses the app's own `fichero-mcp` launcher.
- `research.mcp-semantic-spatial-tools` — **[PARTIAL]** (#270) the hand-kept spatial and note tools (`fichero_mp_place_node`, `fichero_mp_focus_node`, `fichero_research_create_note`, `.list_notes`) were retired 2026-10-18 with the second tool lists (`research.mcp-one-generated-server`); the generated tools of the routes behind them remain (`fichero_create_note`, `fichero_list_notes`, the Mind Palace routes). The issue's fuller list (group, stack, inspect-in-context, compact scene/viewport summaries, delta responses) and the note update/merge/publish lifecycle are not built: a partial build of a larger ask, not a from-scratch gap.
- `research.mcp-one-generated-server` — **[OK]** (#2896; `fichero-mcp/tests/test_mcp_generated.py` `test_only_one_server_module`) `server.py` is the one MCP server and its tools are generated from the contract (#5453, `openapi.mcp.*`). The hand-maintained `full.py`, `simple.py` (`fichero-mcp-simple`) and the tool lists behind them were retired 2026-10-18 with their five test files; the spatial and note tools they carried (`research.mcp-semantic-spatial-tools`, #270) are reached through the generated tools of the routes behind them.
- `research.mcp-knowledge-endpoints-unwired` — **[OK]** (#1439; retired 2026-10-18, `fichero-server/tests/unit/api/test_no_duplicate_knowledge_routes.py`) the eight `/api/mcp/tools/knowledge/*` routes duplicate `/api/entities` and `/api/claims` and surface as a second MCP tool for one capability (toolset `mcp`). They are retired, not wired; `POST /api/mcp/tools/check/verdicts` stays (it carries `source.check.model-never-a-person`). The `/api/integrations/*` endpoints belong to the Integrations fold.
- `mcp.client.tools-survive-a-restart` — **[OK]** (#5760; built 2026-10-18: `sync_mcp_tools_from_db` in `workflows/tools/mcp.py`, run by the engine after it is ready, and `_resync_registry` after every save, update and delete in `api/routes/mcp/servers.py`; tested in `fichero-server/tests/unit/mcp/test_mcp_tools_load_at_start.py`) an enabled server's tools are loaded into the workflow tool registry when the engine starts and whenever a server is saved or deleted, by the engine, with no button. The button route stays for the workflow inspector.
- `mcp.client.tools-reach-a-workflow` — **[PARTIAL]** (#5760; flag alpha, `test_mcp_tools_are_in_the_palette.py` and `FeatureManagerTests`; a one-node workflow running a tool is pinned by `test_mcp_client_round_trip.py`, the palette not seen in the app) a loaded `mcp_*` tool is in the node palette with no feature flag, and a one-node workflow runs it. Today the palette hides them behind `workflowToolsMcp` (tier dev).
- `mcp.client.round-trip-pinned` — **[OK]** (#5760; `fichero-server/tests/unit/mcp/test_mcp_client_round_trip.py`; it found that no external tool had ever loaded or run: the adapters' session was never initialized and tools were bound to a session already closed, fixed in `mcp/manager.py`) a test saves an in-process stdio MCP server (FastMCP, one `echo` tool, launched by `python`) through `/api/mcp-servers`, loads it, finds `mcp_echo` in `TOOL_DEFS` and runs it. 
- `mcp.client.available-to-chat-is-off-by-default` — **[OK]** (#5761; ruled 2026-10-18) each external MCP server has an "available to chat" switch (`available_to_chat` on the server, set in Settings › MCP in the server's row, and by `PUT /api/mcp-servers/{id}`). A server is created with it off, and a server saved before the switch existed is off. Test: `fichero-server/tests/unit/mcp/test_mcp_tools_reach_the_chat_5761.py`, `test_mcp_call_tool_is_owner_only_5761.py`.
- `mcp.client.tools-reach-the-agent` — **[OK]** (#5761; ruled 2026-10-18, replaces the open question about an external agent) a server that is enabled AND available to chat has its read-only tools bound to the in-app chat agent beside the action tools, **only for a chat whose actor is the owner** (an editor's, a paired device's or an unsigned client's chat is offered none); "read-only" is the server's own claim (`readOnlyHint`), which Fichero cannot verify, so the owner's switch is the trust decision. Each tool is named `mcp__<server>__<tool>`, so it never shadows a built-in tool and two servers with the same tool name do not collide (a name the model API would refuse is sanitised and keeps a short hash of the original, and one over 64 characters is cut with a hash); a server that is off, disabled or deleted contributes none, so the model never sees them. A server that will not start offers nothing, and the chat is told which one and the error type, so the turn goes on without guessing at its tools. A tool the server does not mark read-only is not bound; a call to one is refused and recorded like an off-allowlist mutation. Pinned by `fichero-server/tests/unit/mcp/test_mcp_tools_reach_the_chat_5761.py` (bound beside the action tools only for the owner's chat, `readOnlyHint` only, namespaced, never shadowing a built-in).
- `mcp.client.chat-calls-are-audited` — **[OK]** (#5761) every chat call to an external tool goes through the audited action layer as `mcp.call_tool` (server, tool, arguments), which is owner-only like the other actions that reach outside the library (`POST /api/actions/invoke` refuses an editor, a paired device and an unsigned client), so it leaves an `ActionAudit` row naming the chat actor and shows as a tool-call card (`test_switched_on_its_read_only_tools_are_bound_and_a_call_is_audited` in `fichero-server/tests/unit/mcp/test_mcp_tools_reach_the_chat_5761.py`: the row's `action_name` is `mcp.call_tool` with the server and tool in its params; owner-only: `test_mcp_call_tool_is_owner_only_5761.py`); a tool that fails is recorded as an error and the turn goes on. *Not pinned: that the call shows in Activity as a change (the audit row is what it would read). Not built: a per-tool allow for tools that change things outside Fichero; today only read-only tools reach chat.*
- `research.apple-fm-tool-callback` — **[GAP]** (#821) no `Tool`-protocol conformance for
  Apple's `LanguageModelSession(tools:)` was found anywhere under `fichero/fichero/`; the
  entity-grounding-during-extraction ask (let `extract_all` check the KG before proposing a
  duplicate) is unbuilt.
- `research.finetune-local-paleography-model` — **[GAP]** (#1813) explicitly filed as FUTURE,
  no-rush; no rubric/typology/gold-transcription dataset or LoRA fine-tuning pipeline exists.
  Recorded as a real future direction, not urgent.

### Touch-first alternatives (legacy milestone "Agent View - Researcher")

- `research.touch-first-context-actions` — **[PARTIAL]** (#2342) "Add to Chat" and "Move to
  Folder" context-menu actions exist (`LibraryView+ContextMenu.swift`,
  `SidebarItemRow+Presentation.swift`, `ChatInspector+ScopedDocuments.swift`) — real
  alternatives to drag/drop for scoping chat or moving documents. Not independently verified
  this pass: whether these are reachable and adequate specifically in iPad/iPhone COMPACT
  mode (the issue's own acceptance criteria), versus present but Mac-only in practice.

### Watchlist (legacy milestone "Notifications & Watchlist View", #76)

A five-issue, explicitly sequenced cluster (backend trigger → review surface → follow-up
actions → tests, #1870 the origin ask) with nothing built at any layer — no model, no API
route, no Swift view. Grouped here rather than as five isolated gaps because the sequence
itself is the issue filer's own design and should stay legible as one program if picked up.

- `research.watchlist-not-built` — **[GAP]** (#1870, #2360, #2361, #2362, #2363) verified at
  HEAD: no `Watchlist`-named model, API route, or SwiftUI view exists anywhere in the tree.
  #2360 (backend trigger on new ingest/clips/KG updates), #2361 (review surface + notifications),
  #2362 (agent follow-up actions from a hit, gated on user approval — explicitly built on
  Researcher/audited-action primitives, not a separate agent system per the issue's own
  wording), and #2363 (privacy/audit tests for the whole cluster) are the sequenced build-out
  of #1870's own ask. None started. #2362 in particular is this spec's own territory once
  picked up (follow-up research actions ARE Research/audited-tool behavior) — noted so it
  isn't lost if #1870's cluster gets split across specs later.

### F. Where Research lives (owner 2026-11-21)

- `research.lives-in-the-main-window` — **[PARTIAL]** (#4705; → #6952) Research has no window and no mode of its own. The chat sits below the sidebar tree (or in any pane, `m2p.chat-single-mount`), and a research folder is a row of that tree. Selecting a research folder changes what the panes show and never what the Items pane is: Items lists the folder's children as it does for any folder, Source and Reader follow the selected child, the chat below the sidebar lists that folder's conversations and is grounded on the folder, the Inspector shows the chat's Scope while the chat has the focus, and a Plan pane that is open shows that folder's plan (`research.plan.is-a-pane-and-a-window`). Acceptance: with a research folder selected, the window's pane list is unchanged and the Items pane shows the folder's children; no selection or menu command replaces the content column with a Research screen; the View menu has no Research mode. *Built:* the chat below the sidebar with its divider (`Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift:53-78`); a folder marked as a workspace is selected as an ordinary folder (`m2p.research-workspaces-are-library-folders`). *Not built:* the `.research` sidebar mode still replaces the content column with a project list beside a three-pane view (`Views/Shell/ContentView/ContentView+Navigation.swift:239-283`: `ResearchProjectListView`, `ResearchWorkspaceView`), reached from View › Research ⌃⌘8 (`App/Menus/ViewMenuCommands.swift:211-224`) at the dev tier; the chat does not scope itself to a selected research folder. *Tests:* `fichero/Tests/Unit/general/Views/Shell/LibraryPaneNeverMountsModeSurfaceTests.swift` (the allowlist emptied of `ResearchWorkspaceView(`), `fichero/Tests/Unit/general/Views/Shell/ViewModeNormalizationTests.swift`, `ResearchFolderSelectionTests.swift` (to write: the pane list before and after the selection; the chat's folder).
- `research.runs-are-activity-jobs` — **[GAP]** (#2073; → #6953) anything the agent does that outlasts one chat reply (writing a plan, a search pass, an import pass, a read-and-tag pass) is a job in the one job model of `ui/activity-pane.md`: it has a row in Activity with its name, its research folder, its state, the model and the place it ran on and its cost; Pause, Continue and Stop are Activity's; it survives the pane, the window and the app closing as any job does; a spend cap that stops it says so in the row. Research draws no run list, no progress table and no log of its own: the lead or plan row that owns a run shows Activity's one state glyph and **Show in Activity**, and nothing more. Acceptance: starting a plan returns at once with a job id; the job is in `GET /api/activity` with its research folder; stopping it in Activity stops it; no view under `Views/Chat/` or `Views/Research/` declares a table of runs. *Today:* writing a plan is one blocking request behind a spinner in a sheet (`Models/ResearchStore.swift:83-102` `isGeneratingPlan`; `Views/Chat/Research/ResearchTasksPane+Views.swift:53-84`), and the chat's tool loop runs inside the chat request (`research.agent-audited-tools`); neither has an Activity row. *Tests:* `test_research_runs_are_activity_jobs.py` (to write: the job row, its folder, stop), `ResearchDrawsNoRunListTests.swift` (to write: a source check).
- `research.models-come-from-the-models-system` — **[BROKEN]** (#6588; → #6954) neither chat nor Research has a model picker. The model that answers is the one the Models and Compute window gives the kind of work "Chat and research" (its **Use for…** verb; the default per kind of work, `models-and-compute-window.md` section E); the chat's bottom bar names it in quiet text, and clicking the name opens Models and Compute with that model selected. A model that cannot answer (not downloaded, no key, no credit) is said in the same words and with the same fix as there. Acceptance: no view under `Views/Chat/` constructs a model picker or loads the provider list; two chats in two windows name the same model; changing it in Models and Compute changes the name in both without a relaunch. *Today:* each `ChatView` keeps its own provider and model in view state and loads the providers itself (`Views/Chat/ChatView.swift:76-78`, `loadProviders`), and draws `ChatModelPicker` in its bottom bar (`Views/Chat/ChatView+PaneChrome.swift:110-117`, `Views/Chat/ChatViewToolbar.swift:155-271`). Until `models.window.is-activitys-shape` is built the name opens Settings › AI. *Tests:* `ChatHasNoModelPickerTests.swift` (to write: a source check; the name follows the one default).

### G. The Plan: a pane, and a window if wanted (owner 2026-11-21)

The Plan is the project-management side of one research folder: its **brief** (the question and its sub-questions, an ordinary note in the folder), its **leads** grouped by **milestone** (a lead is one thing to find or one search task; a milestone is an archive phase or a question), and the records the work leaves. It is built as Activity is: one pane, and a window that is that pane with a source list and the Inspector.

- `research.plan.is-a-pane-and-a-window` — **[GAP]** (#2070; → #6955) the Plan is a pane kind of the main window (`PaneSpec.Kind.plan`: in every pane menu's Pane ▸ and Split ▸, in View ▸ Panes, in a saved workspace's layout) AND an optional window, **Plan** (Window › Plan, ⌃⌘8, the chord the retired Research mode held), which is the same pane with a source list on its left and the Inspector on its right, as `activity.window.is-the-pane-plus-inspector`. One view, two hosts; the window adds no table, verb or state the pane lacks. Acceptance: the kind is in `PaneSpec.Kind.selectableKinds`; the window scene mounts the pane's own view; every verb of the window is in the pane's menu or its rows' context menu. *Tests:* `PlanPaneKindTests.swift`, `PlanWindowIsAPaneTests.swift` (to write, after `ActivityWindowIsAPaneTests`).
- `research.plan.five-views-one-table` — **[GAP]** (#2070; → #6955) the pane is ONE table with five views, chosen in the pane menu's View As ▸ (in the window, in its source list under each research folder): **Leads** (grouped by milestone: the lead, its outcome, its state glyph, how many sources it has), **Searches** (`research.plan.search-log`), **Sources** (`research.plan.source-register`), **Staged** (`research.plan.staged-imports-wait-for-yes`) and **Changes** (`research.plan.changes-with-undo`). The head has no tab bar and no segmented control; the bottom bar is the app's (+ − on the left where the view has them, the Filter field, Options; `panes.bar.one-filter-and-options-component`); the Inspector shows the selected row. Staged and a lead that needs the person are counted in a badge on the research folder's sidebar row and on the view's name. Acceptance: one `Table` in the pane's view tree; the five views are a grouping and a column set over it; the view is remembered per pane. *Tests:* `PlanViewsTests.swift` (to write: each view's columns as a pure table; the badge count).
- `research.plan.window-opens-closes-restores` — **[GAP]** (#2070; → #6955) the Plan window opens from Window › Plan, from **Open Plan in Window** in the Plan pane's menu and in a research folder's context menu, and by double-clicking a research folder's Plan row; asked for again it comes forward (one window, as Activity's). Its source list has the research folders of every open project, grouped by project. Closing it stops nothing and loses nothing: runs go on in Activity and the pane in the main window is unaffected. At the next launch it is open if it was open, on the screen and at the size it had, with the folder, the view, the selected row and the Inspector as they were; a folder that is gone falls back to the first one and says nothing. Closing a project removes its folders from the list. *Tests:* `PlanWindowRestoreTests.swift` (to write: the restored state as a pure function of what was stored and which folders exist).
- `research.plan.follows-the-selection-both-ways` — **[GAP]** (#2070; → #6956) the Plan and the library show the same thing. Selecting a row that stands for a document (a source that was imported, a staged item, the target of a change, a lead's document) selects that document in the main window, so Items, Source, Reader and the Inspector show it: in the pane always; from the window, in the front main window of that project without bringing it forward, so the window can sit on a second screen while the page changes on the first. **Reveal in Project** (double-click, ⌘R in the window) brings the main window forward. The other way: selecting a research folder in the sidebar turns the Plan to that folder, and selecting a document that has a row in the view on screen selects that row. A row with no document (a search, a source not yet imported) changes nothing in the library. The link can be turned off per pane with the pane menu's Link… / Unlink (`panes-workspaces.md` section G). Acceptance: a pure function from (row, link on) to the selection the main window is asked for; no second selection model. *Tests:* `PlanSelectionLinkTests.swift` (to write).

### H. What the Plan shows of the work (owner 2026-11-21, from the review of research on the builder)

- `research.plan.leads-and-milestones` — **[PARTIAL]** (#2070, #2072; → #6957) a lead has a title, a milestone, one outcome when it ends (**found**, **not found** or **requested**) and passes of three kinds, done in order: **search** (these terms, this catalogue), **import** (these records into Staged) and **read and tag** (these documents). A lead with no outcome is open; one that ends has exactly one. The brief is a note in the folder, opened in the Reader by **Open Brief**. *Built:* plans, tasks with a status the person cycles, and steps of four kinds (`web_search`, `browser_navigate`, `document_fetch`, `local_search`) with a done mark (`Models/ResearchModels.swift:225-239`, `Models/ResearchStore.swift:129-167`, `Views/Chat/Research/ResearchTasksPane+Views.swift`); a plan written by the agent from a term (#1729). *Not built:* a milestone over leads (a plan stands in for one), the outcome, the import and read-and-tag kinds, the order between passes. *Tests:* `fichero/Tests/Unit/general/Models/ResearchModelsTests.swift` (extend), `test_research_lead_outcome.py` (to write: one outcome, never two; a pass refused before the one it depends on).
- `research.plan.search-log` — **[GAP]** (#2072; → #6958) every search pass writes one row per search made: the date, the catalogue, the terms as typed, the number of hits, and its lead. A search pass with no row is not done, whatever the agent says. Searches lists them newest first, filtered by the Filter field; a row's Inspector shows the hits kept as sources. Rows are written by an audited action, by the agent or by the person (+ in the bottom bar). *Tests:* `test_research_search_log.py` (to write: a pass with no row cannot be marked done).
- `research.plan.source-register` — **[PARTIAL]** (#2072; → #6958) Sources is the register: one row per thing found, with its shelfmark, its holding institution, its title, its URL, the lead that found it and its state (**found**, **requested**, **staged**, **imported**). A row whose shelfmark or URL is already in the register or in the project is refused and names the row it repeats. An imported row opens its document (`research.plan.follows-the-selection-both-ways`). *Built:* a source row with a label, a URL or a folder, and a type (`Models/ResearchStore.swift:189-198`, `research.source.*` actions; the Sources tab, `Views/Chat/Research/ResearchTasksPane+Tabs.swift`). *Not built:* shelfmark, institution, state, the duplicate refusal, the link to the imported document. *Tests:* `test_research_source_register.py` (to write: the duplicate refusal by shelfmark and by URL; the state after an import).
- `research.plan.staged-imports-wait-for-yes` — **[GAP]** (#2072; → #6959) what the agent imports lands only in the research folder's **Staged** folder, an ordinary child folder, and waits there. Staged lists each waiting import (what, from where, how many pages, which pass) with two verbs, by the Mail rule over the selection: **Accept** moves the items to the folder the research folder names as its destination, as one undoable step; **Reject** puts them in the Trash (a folder, restorable) and undoes that pass's other changes as one set. Nothing the agent imported is anywhere but Staged before an Accept, and no setting lets the agent accept its own work. An import that cannot be undone by the engine (`iiif.import` is declared not undoable) is rejected by trashing its folder, and the row says so. Acceptance: after an agent import the destination folder's listing is unchanged; Accept then Edit › Undo puts the items back in Staged; Reject then Put Back restores them. *Tests:* `test_research_staged_imports.py` (to write: the agent's actor cannot write outside Staged; accept, undo, reject, put back).
- `research.plan.changes-with-undo` — **[GAP]** (#1848, #4431; → #6960) Changes lists what the agent did in this research folder, one row per audited action by a model's account (when, the action in plain words, its target, the lead and pass, the model), read from the audit rows every action already leaves (`ActionAudit`), never a second record. **Undo** on a row reverses it; **Undo Pass** reverses a pass's rows as one set (`actions/undo.py` `undo_set`); both are steps on the window's undo stack, so Edit › Redo puts them back (`ui/undo-everywhere.md`). A row that cannot be undone is drawn so, with why and what to do in its place. The tool-call card in a conversation gains the same Undo beside its "recorded" badge. A read is not a change and is not listed. *Built:* the engine's undo of one action and of a set, and both in the MCP; the card's "recorded" and "not recorded" badges (`Views/Chat/ToolCallCard.swift:78-94`), with no button. *Tests:* `test_research_changes_list.py` (to write: only the folder's model-actor mutations; undo of a set), `ToolCallCardUndoTests.swift` (to write).

### I. One word, one meaning (owner 2026-11-21)

"Workspace" means four things in the code and the specs today, and "project" two:

| Today's word | What it is | Where | Its one name from now |
|---|---|---|---|
| Workspace (the Workspaces menu, ⌘⌥1–5) | a window's saved pane layout | `Views/Shell/WindowLayout/WindowWorkspace.swift`, `panes-workspaces.md` | **workspace** |
| Workspace (File › New › Workspace) | a folder marked `is_workspace`, with curated items | `Models/DocumentStore+CRUD.swift:51-54`, `Models/ItemTypeRegistry.swift:105-106` | **research folder** |
| Workspace ("Save as Workspace") | a chat saved as such a folder, `workspace_kind=agent` | `Models/WorkspaceStore.swift`, engine `api/routes/system/chat.py:333` | **research folder** (the same thing) |
| Research project | a row with plans, tasks, sources and notes, and no folder | `Models/ResearchModels.swift`, `Services/ResearchService+Projects.swift` | **research folder** (its record) |
| Project | the library a window opens (the Project menu) | everywhere | **project** |

- `research.words.workspace-means-a-layout` — **[BROKEN]** (#4335; → #6961) in everything a person reads (menus, buttons, help, empty states, the manual) **workspace** means only a window's saved pane layout, **project** means only the library a window opens, and the folder that holds a line of research is a **research folder**. So: File › New › **Research Folder**; **Keep in Research Folder…** (File menu and the chat's pane menu) files the chat on screen into a research folder, new or chosen, and replaces "Save as Workspace"; no string says "research project" or "research workspace". Names in code and in the contract (`WorkspaceStore`, `AgentWorkspace`, `is_workspace`) may stay until their files are next changed. *Today:* "Save as Workspace" (`Views/Chat/ChatView+PaneChrome.swift:92-103`, `Views/Chat/ChatView.swift:252-254`), "the workspace's tasks" (`ChatView.swift:37`), the "Workspace" item type and "New Workspace" (`Models/ItemTypeRegistry.swift:105-106`, `Views/Sidebar/Components/SidebarCreationHandlers.swift:74`), "New Research Project", "No Research Project" (`Views/Chat/Research/ResearchProjectListView.swift:181`, `ContentView+Navigation.swift:274-278`), the engine's "Research Workspace" prototype label (`fichero-server/src/fichero_server/db/__init__.py:355`). *Tests:* `WorkspaceWordTests.swift` (to write: a source check that a user-facing string with "Workspace" is only in the layout files, and none says "Research Project").
- `research.folder.one-record` — **[GAP]** (#2571; → #6962) a research folder is one thing with one record: the research row (plans, leads, sources, notes) is keyed to its folder, made with it, put in the Trash with it and put back with it; there is no research row without a folder and one kind of marked folder, not `agent` beside `research`. A project opened with older research rows gets one research folder per row, once, on open, and the rows keep their ids. *Today:* three records: a folder with `workspace_kind=agent` made by saving a chat (`api/routes/system/chat.py:1143-1179`), a `research` folder prototype (`db/__init__.py:355-364`), and `ResearchProject` rows that have no folder (`modes-to-panes.md` increment 5b says so). *Tests:* `test_research_folder_one_record.py` (to write: create, trash, put back; the on-open conversion run twice changes nothing).

### J. The built UI brought to the new UX (owner 2026-11-21; "less is more")

- `research.ux.chat-has-two-views` — **[BROKEN]** (#4705; → #6963) the chat has two views, **Conversation** and **Scope** (what the chat is grounded on: pinned, the current view, cited), chosen in its pane menu's View As ▸. Plan leaves the chat for the Plan pane; Compare is retired (ruling 2026-09-18); Knowledge's two counts become one quiet line at the foot of Scope until the engine returns identities (`research.knowledge-tab-not-browsable`). *Today:* five lenses (`Views/Chat/ChatView.swift:7-42`), Compare still mounting `ModelComparisonView` (`ChatView.swift:265-267`). *Tests:* `fichero/Tests/Unit/general/Views/Chat/ChatSurfaceTabTests.swift` (changed: two cases).
- `research.ux.chat-head-and-bar` — **[BROKEN]** (#5435; → #6963) the chat's head and bar are every pane's (`panes.head.one-menu-button`, `panes.chrome.head-keeps-only-what-moves`, `panes.chrome.mac-bars-like-xcode`). Head: on the left only what moves through conversations (the conversation's name as a menu of the folder's conversations, ‹ ›); on the right the ONE pane menu, whose button is the chat's icon: Pane ▸, View As ▸ (Conversation, Scope), Split Right ▸, Split Below ▸, Focus on Pane, Pin Pane (stay on this conversation), Keep in Research Folder…, Close Pane. No ✕, no kind picker, no lens picker and no pin button on the head. Bottom bar: **+** (New Chat) on the left; on the right one scope chip ("Folder name · 3 pinned"; clicking shows Scope) and the model's name (`research.models-come-from-the-models-system`). Nothing else: no Save button, no second count. *Today:* the head is given a lens selector of five, a close action and a pin binding (`Views/Chat/ChatView+PaneChrome.swift:11-55`); the bar holds +, the model picker, an eye label, a pin count and Save as Workspace (`ChatView+PaneChrome.swift:57-105`). *Tests:* `ChatChromeShapeTests.swift` (to write: the menu's entries in order; the bar's items).
- `research.ux.one-title-per-screen` — **[BROKEN]** (#5435; → #6963) a screen names a thing at most once. The window's title names the project and the selection; a pane's head names what it shows only when pinned (`panes.chrome.breadcrumb-only-when-pinned`); nothing inside a pane repeats its kind or its view. *Today, each a second title:* "Chat Scope" above the scope list under a view already named for it (`Views/Chat/Inspector/ChatInspector+Header.swift:6`); a "Research" section header inside the Research mode (`Views/Chat/Research/ResearchProjectListView.swift:54`); "Research Plan" inside the Plan tab (`Views/Chat/Research/ResearchTasksPane+Views.swift:120`); the chat head's "Chat" kind title beside the conversation's title and icon (`ChatView+PaneChrome.swift:13-31`). *Tests:* `ResearchOneTitleTests.swift` (to write: a source check of the four).
- `research.ux.rows-select-like-finder` — **[BROKEN]** (#5435; → #6964) every list of Research (leads, searches, sources, staged, changes, the scope list, notes) is selected as Finder's are: a click selects, ⇧ and ⌘ extend, the arrows move, Return renames, ⌫ deletes, a drag reorders or files, the context menu has the same verbs as the menu bar, and a verb acts on the whole selection by the Mail rule. A delete is a step on the undo stack, never an alert that says it cannot be undone. Adding is **+** in the bottom bar, which makes a row in rename; there is no text field with its own submit button at the foot of each list. Selection is the system's grey-fill, dark-text selection. *Today:* a segmented Tasks | Checklists | Sources | Notes control at the top (`Views/Chat/Research/ResearchTasksPane.swift:27-33`); an add field with a submit button per tab (`ResearchTasksPane+Tabs.swift:147-166`); a task's status changed by a button that cycles it; the project list's delete confirms with "cannot be undone" (`ResearchProjectListView.swift:163-175`); Chat Scope's own Select All, Remove and Clear buttons in a header (`ChatInspector+Header.swift:12-41`). Checklists become leads' check items or notes; the tab goes. *Tests:* `PlanRowsSelectionTests.swift` (to write: the verbs enabled per selection as a pure table; delete registers an undo).
- `research.ux.old-surfaces-deleted` — **[BROKEN]** (#4719; → #6952) with F built these are deleted, not hidden: `ResearchWorkspaceView`, `ResearchChatPane`, `ResearchProjectListView`, the `.research` sidebar mode with its View menu entry and its `research-browser` saved selection (which restores to the library), the unreferenced `ChatViewToolbar` (`Views/Chat/ChatViewToolbar.swift:10-98`; nothing constructs it), chat's Compare view and, with `research.models-come-from-the-models-system`, `ChatModelPicker`. `ResearchTasksPane` becomes the Plan pane's table. `ResearchBrowserPane` stays until `m2p.browser-is-a-source-rendition` (→ #4809) gives it its home. *Tests:* `LibraryPaneNeverMountsModeSurfaceTests` (the allowlist empty), `ResearchOldSurfacesGoneTests.swift` (to write: a source check by name).

### K. iPhone and iPad (owner 2026-11-21; `ui/iphone-ipad.md`)

- `research.ios.drill-then-swipe` — **[GAP]** (#6493; → #6965) on the iPhone a research folder is a folder: Sidebar → the folder's Items, whose first row is **Plan**. Plan pushes the Leads list; a swipe left or right moves between Leads, Searches, Sources, Staged and Changes; a row pushes its detail, and a row that stands for a document pushes that document's Source, from which the usual swipe reaches Reader, Segments and Info. The chat opens from the Chat button as one screen; a swipe moves between Conversation and Scope. Accept, Reject and Undo work on the phone (the person's yes can come from anywhere); a run is started on the Mac and watched in Activity; the model is named, and chosen on the Mac. On the iPad the Mac's panes sit side by side and the Plan is a pane among them; a Plan window is not promised there. This replaces "Research is a list that pushes its detail" in `ios.nav.other-kinds` for Research. *Today:* the Research mode's compact stack (project list → the three panes stacked, `ContentView+Navigation.swift:240-259`, `Views/Chat/Research/ResearchWorkspaceView.swift:14-28`). *Tests:* `CompactPlanStepsTests.swift` (to write: the steps and the swipe order as a pure table, beside `CompactShellPolicyTests`).

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | `ChatSurfaceTab` tab set + `researchProject`-present → `ResearchTasksPane` vs. invitation | proposed suite under `fichero/Tests/Unit/general/Views/Chat/` (no file yet) |
| Availability (Swift) | y | `saveAsWorkspace()` reachable only once `backendConversationId` is non-nil | same suite |
| Backend (pytest) | y | chat-tools loop default-on, read parity, write allowlist refuses everything else | `fichero-server/tests/unit/actions/test_chat_tools_loop.py` (exists — cited by `agent-chat-survey.md`) |
| Backend (pytest) | y | `DocumentStore.createWorkspace` → folder + `workspace_kind=agent` marker | `fichero-server/tests/**` workspace CRUD tests (not enumerated here — see `docs/reference_manual` endpoint reference) |
| MCP | n | Research has no MCP-specific contract beyond the shared action registry | — |
| CLI | n | no CLI surface for Research specifically | — |
| Click-around (XCUITest, Mac) | y | open a chat → Plan tab invitation → Save as Workspace → Plan tab shows tasks | `fichero/Tests/UI/**` (no dedicated suite yet — #4727) |
| iPhone (iOS) | y | chat dock/compact flow touch path | `fichero/Tests/UI/ios` (shared with chat's existing compact tests, not enumerated here) |
| iPad | y | same as iPhone leg, iPad idiom | `fichero/Tests/UI/ipad` |
| Load (#4634) | n | Research has no dedicated load profile beyond chat's own | — |

This spec proposes (not yet added — **[PROPOSED]**, neither exists):
- Swift `@Tag static var research: Self` in `fichero/Tests/Unit/general/TestTags.swift`
  (alongside the existing `.knowledgeGraph`/`.workflow`/`.reader`/… vocabulary).
- pytest marker `"research: Research surface contract (spec: research) — chat-tools loop,
  workspace folder-node creation, plan/task/checklist CRUD"` in
  `fichero-server/pyproject.toml`'s `markers` list, matching the Swift tag by name (house
  convention — same area names front and back).

## Open questions (max 7)

1. **Answered** (ui/modes-to-panes.md Rulings 2026-09-18): In the Source/Preview pane, no browser pane kind. **Where does the embedded browser render once `ResearchWorkspaceView` retires?** —
   RESOLVED (creative-director ruling, 2026-09-18, third round, `modes-to-panes.md`
   Rulings): inside the Source/Preview pane as `PaneSurface.webBrowser`, no browser pane
   kind, no tab strip of its own. See `research.embedded-browser-home-surface` above.
2. **Does `ResearchBrowserPane`'s save action move to the chat composer's pin menu, or stay
   a research-node-only capability?** Narrowed by the same ruling: only an explicit save
   makes a node, and it takes one of two shapes — the page captured as a native
   `.webarchive` (URL + capture time), or, preferred where the page supports it, the
   page's EXTRACTED output saved as the artifact with the page recorded as its provenance
   (`m2p.saving-a-source-makes-a-node`, → #4811). What remains open is narrower than
   before: WHICH of the two save shapes a given save action offers/defaults to, and
   whether that choice is per-page-type or user-chosen each time — not whether saving is
   research-node-only (scratch browsing outside a workspace was never in scope) nor what a
   save produces.
3. **Answered** (design lead 2026-10-04, applying the spec's lean): Yes, file the engine issue before building any UI. **How does the Knowledge tab get browsable entity/claim identities?** Blocked on an
   engine change (return entity/claim IDs alongside `RetrievalInfo` on a chat reply), not a
   UI decision. Recommendation: file the engine issue rather than building a UI ahead of the
   data.
4. **Do research notes/checklists get their own child-node kind (e.g. a lightweight text
   node under the workspace folder), or stay rows in the `ResearchNote`/`ResearchChecklist`
   tables reachable only through the Plan tab?** Recommendation: node-kind, once the
   node-model EPIC (#2081/#2591) lands — keeps "everything in the workspace is a child node"
   literal rather than half-true. Not urgent; the Plan tab's current row-based UI already
   works.
5. **Per-model tool grants (owner-configurable allow/deny per model identity, beyond
   role)** — `agent_chat_as_user.md` marks this "TO BUILD" with no settings surface.
   Recommendation: defer past this milestone; the role-based allowlist is a sufficient
   authority boundary for the DRAFT surface, and a per-tool UI is real design work of its
   own (#2887).
6. **Answered** (ui/modes-to-panes.md increments 5a-5c, #4719): Retired in modes-to-panes' increments. **Does `research.plan-tab-is-only-plan-surface` retire `ResearchWorkspaceView` in this
   milestone or `modes-to-panes.md`'s?** — ANSWERED: `modes-to-panes.md`'s, in increments
   5a/5b/5c (`ResearchWorkspaceView`/`ResearchProjectListView` both retire there). This
   spec does not duplicate that increment plan — it tracks the behavior id
   (`research.plan-tab-is-only-plan-surface`) and points at #4719 for the retirement
   itself.
7. **Several chats, each scoped to a part of the project — one workspace, many
   conversations?** Raised by the creative director (2026-09-18, latitude + method
   comment on #4705) as a real possibility: chat = node, scope = its own Sources tab, once
   increment 6's one-mount-per-conversation state work (lifting conversation state out of
   `ChatView`'s `@State`) is the prerequisite. Not yet designed — this spec owns the
   question, not the answer.

- `research.notes-are-child-nodes` — **[GAP]** (#2081, #2591; open question 4) research notes and checklists become a child-node kind under the workspace folder once the node-model EPIC lands. Today they stay rows in `ResearchNote`/`ResearchChecklist` reachable only through the Plan tab. Not urgent.
- `research.workspace-many-chats` — **[GAP]** (#4705; open question 7) one workspace holds several chats, each scoped to part of the project, with the chat as a node and scope in its own Sources tab. Blocked on increment 6 (one mount per conversation). Not designed yet.

## Sources folded in

Design content carried into this spec; files kept, listed here per program instruction
(report only — not moved or deleted):

- `agent-work/design/agentic-surface-consolidation-fabel-review.md` — origin of "one
  surface, named Research", the node-kind-not-sidebar-mode ruling, and the trust-boundary
  framing for the embedded browser. Superseded by this spec for the parts it decided that
  are now ratified/grounded here; its migration-step sequencing (engine steps 1-3,
  reorg-gated) remains the authoritative source for backend ordering not restated here.
- `agent-work/status/agent-chat-survey.md` — corrected this spec's understanding that the
  chat-tools loop is wired and default-ON (not "planned", as the older
  `agent_chat_as_user.md` states) — verified directly against current
  `chat.py:561-588` rather than trusted as-is.
- `agent-work/design/in-app-agent-parity-plan.md` — origin of the read-parity +
  allowlisted-write shape (`CHAT_WRITE_ALLOWLIST`) now folded into `research.agent-audited-tools`.
- `agent-work/status/RESEARCH_STATUS.md` — status log for the Swift-parallel-safe subset
  (`ToolCall`/`ToolCallCard`, `SourceLedgerEntry`, the Plan tab) that is now simply "what
  exists today" above; folded in as historical provenance, not re-described as a plan.

## Future (ideas, not scheduled)
- `research.future.library-node-model` — **[GAP]** (#2081) library node model: prototypes, aliases and entities-as-nodes (Tinderbox-for-archives); canonical for cluster.
- `research.future.agent-operates-projects` — **[GAP]** (#2291) in-app agent operating Projects/Milestones/Tasks from chat; agent-surface vision, not current work.
- `research.future.three-chat-modes` — **[GAP]** (#2314) three chat modes (Simple/RAG/Agent) with an on-device router; chat-surface nice-to-have.

## Triaged from the backlog (2026-10-04)
- `research.uitest.click-around-plan-save` — **[GAP]** (#4727) an XCUITest opens a chat, takes the Plan invitation, Save as Workspace, and sees the Plan tab list tasks (research.planpromotestoworkspace).

## Triaged from the render review (2026-11-20)

- `research.answer-citations-open-the-passage` — **[GAP]** (#1828) see `kg/kg-rendering.md` section F: an answer's Sources list names a document and a score, carries no page or passage (`DocumentSource`), and its rows are not controls (`MessageCard.sourcesView`); the Cited ledger is text only (`SourcesLedgerView`).

## Review 2026-11-20: asking the project a question (measured)

Moved to `ui/search.md` section L, with its ids, so the search milestone's Build order holds the
chat fixes (#6789) in one spec.

## Build order

Ordered as the owner asked (2026-11-21): first the UX update of what is built, then the Plan as a pane and a
window, then the operations views. Every step is 25 files or fewer. `→ #N` is an issue filed
on the `research` milestone; each line also cites an open issue. Behaviours of this spec that are not
listed here are owned by another spec's build order (`modes-to-panes.md` increments 5 and 6, the MCP client) or
are in Future.

### Stage 1 — What is built, brought to the new UX

#### Step 1.1 — Research lives in the main window: the mode and the old surfaces go
- Behaviours: `research.lives-in-the-main-window`, `research.ux.old-surfaces-deleted`, `research.project-is-sidebar-node`, `research.plan-tab-is-only-plan-surface`
- Tests: fichero/Tests/Unit/general/Views/Shell/LibraryPaneNeverMountsModeSurfaceTests.swift, fichero/Tests/Unit/general/Views/Shell/ViewModeNormalizationTests.swift, ResearchFolderSelectionTests.swift, ResearchOldSurfacesGoneTests.swift
- Size: M

The `.research` arm of `contentView`, the mode, its menu entry and saved selection, the three old views and `ChatViewToolbar` deleted; the chat below the sidebar takes its folder from the selected research folder. `ResearchTasksPane` is kept, mounted nowhere but chat's Plan view until Step 2.1. About 14 files.

#### Step 1.2 — The chat's chrome: two views, the one pane menu, the bar, one title
- Behaviours: `research.ux.chat-has-two-views`, `research.ux.chat-head-and-bar`, `research.ux.one-title-per-screen`, `research.chat-scope-single-mount`, `research.sources-tab-is-chat-scope`
- Tests: fichero/Tests/Unit/general/Views/Chat/ChatSurfaceTabTests.swift, ChatChromeShapeTests.swift, ResearchOneTitleTests.swift
- Depends on: 1.1
- Size: M

`ChatSurfaceTab` to two cases; the head given no lens selector, close or pin; the bar's items; Scope mounted once per host (the Inspector and the pane's Scope view), the attach sheet on compact width only. About 12 files.

#### Step 1.3 — The words: workspace is a layout, the folder is a research folder
- Behaviours: `research.words.workspace-means-a-layout`
- Tests: WorkspaceWordTests.swift, fichero/Tests/Unit/general/Models/ItemTypeRegistryTests.swift, fichero/Tests/Unit/general/Models/SidebarWorkspaceNodeTests.swift
- Depends on: 1.2
- Size: S

Strings, the item type's name, Keep in Research Folder… in the File menu and the chat's pane menu, the engine's prototype label. No type or contract rename. About 10 files.

#### Step 1.4 — The model is the Models system's
- Behaviours: `research.models-come-from-the-models-system`
- Tests: ChatHasNoModelPickerTests.swift, fichero-server/tests/unit/api/test_chat_provider_model_details.py
- Depends on: 1.2
- Size: M

The chat reads the one default for "Chat and research"; `ChatModelPicker` and the view's provider loading deleted; the name opens Models and Compute (Settings › AI until `models-and-compute-window.md` Step 1.1 lands). About 9 files.

#### Step 1.5 — The embedded browser takes the new UX
- Behaviours: `research.embedded-browser-home-surface`
- Tests: EmbeddedBrowserNewUXTests.swift (to write)
- Depends on: 1.2
- Size: M

The embedded browser renders in the Source/Preview pane (`PaneSurface.webBrowser`) with the same one pane menu, bar and Finder-style selection as the chat; moved here from Step 4.2 (`modes-to-panes.md` increment 5c is built here, not later).

### Stage 2 — The Plan: a pane, then a window

#### Step 2.1 — The Plan pane kind over the rows that exist, selected like Finder
- Behaviours: `research.plan.is-a-pane-and-a-window`, `research.plan.five-views-one-table`, `research.ux.rows-select-like-finder`
- Tests: PlanPaneKindTests.swift, PlanViewsTests.swift, PlanRowsSelectionTests.swift, fichero/Tests/Unit/general/Views/Shell/PaneHeadKindSwitcherParityTests.swift
- Depends on: 1.2
- Size: M

`PaneSpec.Kind.plan`; `ResearchTasksPane` rebuilt as one table with the views the data has today (Leads from tasks, Sources from source rows; Searches, Staged and Changes listed and empty with their reason); the app's bottom bar; the verbs in one table. About 20 files.

#### Step 2.2 — One record per research folder
- Behaviours: `research.folder.one-record`, `research.plan-promotes-to-workspace`, `research.chat-is-lightweight-end`
- Tests: test_research_folder_one_record.py, fichero-server/tests/unit/api/test_routes_documents_workspace.py, fichero-server/tests/unit/api/test_routes_research_agents.py
- Depends on: 1.3
- Size: M

Engine: the research row keyed to its folder, the one marked kind, the on-open conversion (check the every-open migrations that touch workspace folders first). App: Keep in Research Folder… makes or picks the folder. About 16 files.

#### Step 2.3 — The Plan window, and the selection linked both ways
- Behaviours: `research.plan.window-opens-closes-restores`, `research.plan.follows-the-selection-both-ways`
- Tests: PlanWindowIsAPaneTests.swift, PlanWindowRestoreTests.swift, PlanSelectionLinkTests.swift
- Depends on: 2.1, 2.2
- Size: M

The window scene as the pane plus a source list and the Inspector, after `ActivityMonitorWindow`; the link as a pure function, asked of the front main window of the project. About 15 files.

#### Step 2.4 — iPhone and iPad
- Behaviours: `research.ios.drill-then-swipe`, `research.touch-first-context-actions`
- Tests: CompactPlanStepsTests.swift, fichero/Tests/Unit/general/Views/Shell/CompactShellPolicyTests.swift
- Depends on: 2.1
- Size: S

The compact steps for a research folder and its Plan; the swipe order. About 8 files.

### Stage 3 — The operations views

#### Step 3.1 — Runs are Activity jobs
- Behaviours: `research.runs-are-activity-jobs`, `research.manager-with-workers-orchestration`
- Tests: test_research_runs_are_activity_jobs.py, ResearchDrawsNoRunListTests.swift, fichero-server/tests/unit/actions/test_chat_tools_loop.py
- Depends on: 2.2
- Size: M

Engine: writing a plan and running a pass become jobs of the one job model with the research folder on the row, a budget and Stop; the plan sheet's spinner goes. Only the single-agent run is built here; the manager-with-workers design stays open under #2069. About 18 files.

#### Step 3.2 — Leads, milestones and outcomes
- Behaviours: `research.plan.leads-and-milestones`, `research.notes-are-child-nodes`
- Tests: fichero/Tests/Unit/general/Models/ResearchModelsTests.swift, test_research_lead_outcome.py
- Depends on: 2.1, 2.2
- Size: M

The milestone, the outcome and the three pass kinds on the engine's rows and in the contract; the Leads view's grouping and columns; the brief as a note. About 18 files.

#### Step 3.3 — The search log and the source register
- Behaviours: `research.plan.search-log`, `research.plan.source-register`
- Tests: test_research_search_log.py, test_research_source_register.py, PlanViewsTests.swift
- Depends on: 3.2
- Size: M

Two audited actions and their rows; the duplicate refusal; the two views' columns. About 16 files.

#### Step 3.4 — Staged imports wait for the person's yes
- Behaviours: `research.plan.staged-imports-wait-for-yes`, `research.per-model-tool-grants`
- Tests: test_research_staged_imports.py, PlanViewsTests.swift
- Depends on: 3.3
- Size: M

The Staged folder, the rule that a model's account writes imports only there (the first per-model grant, enforced in the action layer), Accept and Reject, the badge. About 18 files.

#### Step 3.5 — What the agent did, with undo
- Behaviours: `research.plan.changes-with-undo`, `research.agent-audited-tools`
- Tests: test_research_changes_list.py, ToolCallCardUndoTests.swift, fichero-server/tests/unit/api/test_action_chat_tools.py
- Depends on: 3.4
- Size: M

The Changes view over the audit rows, Undo and Undo Pass on the window's stack, the card's Undo. About 14 files.

### Stage 4 — Carried from before 2026-11-21 (not part of the UX update; listed so every open line has a step)

#### Step 4.1 — Pin what is built and unpinned (#4798)
- Behaviours: `research.one-surface-named-research`, `research.chat-context-aware`, `research.browser-pane-trust-boundary`, `research.knowledge-tab-not-browsable`, `research.compare-folds-into-chat`
- Tests: fichero/Tests/Unit/general/Views/Chat/ChatViewBoundaryTests.swift, fichero/Tests/Unit/general/Views/Chat/ChatAttachContextTests.swift, fichero/Tests/Unit/general/Views/Shell/ChatWithDocsRoutingTests.swift
- Depends on: 1.2
- Size: S

Tests only, after Step 1.2 has removed the Compare and Knowledge views, so what is pinned is what stays.

#### Step 4.2 — Chat in any pane (`modes-to-panes.md` increment 6; #4041)
- Behaviours: `research.chat-single-mount`
- Tests: fichero/Tests/Unit/general/Views/ChatMountTests.swift, fichero/Tests/Unit/general/Views/Chat/ChatViewBoundaryTests.swift
- Depends on: 1.2
- Size: M

Built from `modes-to-panes.md`, which owns it; listed here so this spec's line has a step.

#### Step 4.3 — The agent's other tools (#3093, #509, #270, #5760, #821)
- Behaviours: `research.canvas-actions-are-agent-tools`, `research.mcp-servers-configurable-in-app`, `research.mcp-semantic-spatial-tools`, `mcp.client.tools-reach-a-workflow`, `research.apple-fm-tool-callback`
- Tests: fichero-server/tests/unit/actions/test_chat_tools_canvas_allowlist.py, fichero-server/tests/unit/mcp/test_mcp_client_round_trip.py
- Depends on: 3.5
- Size: M

#### Step 4.4 — Later: the watchlist and a tuned local model (#1870, #1813)
- Behaviours: `research.watchlist-not-built`, `research.finetune-local-paleography-model`
- Tests: test_research_watchlist.py
- Depends on: 3.5
- Size: M

Not scheduled; each needs its own design before a brief is cut.
