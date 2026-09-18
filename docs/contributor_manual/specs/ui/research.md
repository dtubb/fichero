# Research — Design Spec (#2067)

> Milestone: research
> Manual: TBD — a Getting Started section explaining that Research is the app's one
> agentic surface: a chat is where you talk to your library, and opening a Plan turns
> that chat into a research workspace with its own working folder of chats, notes and
> outputs.

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

## Superseded rulings

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
- Opening the chat's **Plan** tab with no project yet shows an invitation, not a dead end:
  "Save this chat as a workspace to plan tasks, track sources, and keep notes"
  (`ChatView.swift:216-227`). Accepting promotes the SAME conversation into a research
  workspace — the continuum is one seam, not two products.
- A **research workspace** that is a folder node in the library tree, not a bespoke
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
- `research.project-is-sidebar-node` — **[GAP]** research projects should be sidebar nodes
  like workflows (`modes-to-panes.md`'s `m2p.research-is-sidebar-node`), not the bespoke
  `ResearchProjectListView` sidebar-mode list that exists today. Tracked by → #4705 (the
  modes→panes EPIC) and #2446/#1738 (retire the Research sidebar mode into node kinds).
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
  original framing.
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
- `research.embedded-browser-home-surface` — **ANSWERED (creative-director ruling,
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
- `research.compare-folds-into-chat` — **SUPERSEDED (creative-director ruling, 2026-09-18):**
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

1. **Where does the embedded browser render once `ResearchWorkspaceView` retires?** —
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
3. **How does the Knowledge tab get browsable entity/claim identities?** Blocked on an
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
6. **Does `research.plan-tab-is-only-plan-surface` retire `ResearchWorkspaceView` in this
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
