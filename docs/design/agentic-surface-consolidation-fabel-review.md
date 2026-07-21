# Agentic Surface Consolidation — Fabel Review

Status: **PLAN / captured, not built.** This consolidates the two 2026-07-19
fabel reviews and Daniel's 2026-07-19/07-20 decisions into one committed doc, and
maps them onto the code that exists on this branch today. It changes no behavior.
The surface is the **next phase** — sequenced *after* front-end hygiene + a build.
Engine steps here (1–3 of the migration) are reorg-gated and off-limits to the
front-end lane; only the Swift-parallel-safe steps are actionable now.

Companions (all grounded, all still valid): the surface audit
`research_agent_search_audit_2571.md` (#2571, retired from the tree but recoverable
at `git show 7d714eab3:docs/architecture/swiftui/research_agent_search_audit_2571.md`),
the shared-chrome plan `docs/superpowers/specs/2026-07-12-surface-consistency-design.md`,
and the model-as-user design `docs/contributor/architecture/agent_chat_as_user.md`.

---

## 1. Decision summary (Daniel)

- **One surface, named "Research."** The activity, not a persona — honours
  *AI = instrument, not interlocutor* (#2151/#2152). Rejected: *Researcher /
  Agent / Assistant* (pretend-human / jargon). The words *workspace* and *agent*
  stay internal-only. ⌘8 is retired.
- **No separate sidebar mode for Research/Workspaces/Search/Workflows.**
  Everything is a **node kind** in the one library folder tree (Finder
  smart-folder model). A node's kind decides what opens: a *workspace* node opens
  the agentic `ChatView` surface; a *smart-folder* runs its query; a *workflow*
  opens the editor. Nodes are found by kind, movable anywhere; default folders
  (Workflows / Smart Folders / Workspaces) are seeded but not load-bearing.
  *(Sidebar collapse is the `sidebar` lane's + engine's work — DEFERRED here.)*
- **Research = a `workspace_kind`.** Opening a research-kind workspace = the
  `ChatView` surface plus togglable **Browser** (`ResearchBrowserPane`) and
  **Plan** (`ResearchTasksPane`) panels. Plain chat = panels off. Opening Plan
  promotes chat → research (the continuum). The `ResearchWorkspaceView` 3-pane
  arrangement survives as the research-kind layout.
- **The workspace *is* the agent's working folder** (a node). Everything is a
  child node inside it: chat item(s), project/task/milestone nodes (the "plan" =
  nodes, not a hardcoded panel), context documents, **aliases** to library
  files/folders (`alias_target_id` already exists) so the agent reaches library
  content without moving originals, and the **output files the agent creates**.
  The inspector is just contextual detail for the selected child — nothing
  special-cased; it falls out of the node model.
- **Agent = a user account scoped to the workspace**, acting through the
  **audited action layer** (#1848 / #1847, `actor="chat"`) with the same toolset a
  human has (move nodes, add folders, download files, drive a browser, run
  workflows) — i.e. `chat_tools.py` (built-but-unwired) wired to the workspace.
- **Chat is two things on one continuum.** *Lightweight* = "chat with THIS,"
  context = the live current selection, following selection around. *Heavyweight*
  = a full workspace (scales to thousands of files — cf. the reference agent dirs
  `maps_jemseg_grand_lake` ~1,320 files, `maps_southern_colombia` ~11,583 files).
  Save a lightweight chat → persistent chat node → open as a workspace (its
  selection pins as alias children, outputs land there, plan/tasks live there).

### Chat panel placement — Option A "pragmatic fixed zones" (2026-07-20, final)

Free-form docking (VS Code/Photoshop) was **rejected** as non-Mac + high cost.
Xcode-style fixed toggleable zones instead. Zone model L→R:

```
[ sidebar tree ] [ content: library / preview / reader | CHAT ] [ inspector ]
                                                        └ split WITHIN content
```

- Chat is **either** a column to the LEFT of the (right) inspector **or** a
  horizontal strip along the BOTTOM of library/preview/reader. It is **never** to
  the right of, and never below, the inspector.
- Implementation seam: chat = a split *within the content zone* —
  `HSplitView [content | chat]` (column) or `VSplitView [content / chat]`
  (bottom). The inspector stays the **native trailing `.inspector()`**, far-right.
- ⚠ **Hazard:** a second right-side panel next to the inspector = exactly the
  custom right-`HStack` tried and **reverted in #2033** (the toolbar overran it).
  The content-split resolution avoids re-introducing it. Do not add a second
  panel to the right of the inspector.
- Agent web-browsing renders in the **Reader** (no separate web column); the
  **bottom area** is agent activity / multiple agents (Xcode debug-area style).
  Chat detaches to a `WindowGroup`; a "workspace window" = a saved zone layout.

---

## 2. Current state — code-grounded

**~40% is already built (#3532 / #3540 / #4001), just unwired.**

| Piece | Where | State |
|---|---|---|
| Unified shell | `Views/Chat/ChatView.swift` | `ChatSurfaceTab` = {conversation, sources, knowledge, compare} on `SurfaceTabBar` + bottom `MiniToolbar`. **Built.** |
| RAG *is* Chat | `ChatView.conversationTabContent` → `ChatMessagesList` + `ChatInputView` | Single conversation spine. **Built.** |
| Research embeds Chat | `Views/Chat/Research/ResearchChatPane.swift:28` → `ChatView(...)`, scoped `/research/{project_id}` | No fork; verbatim reuse. **Built.** |
| Research 3-pane | `Views/Chat/Research/ResearchWorkspaceView.swift` (chat \| browser \| tasks) | Survives as the research-kind layout. **Built.** |
| Compare fold | `ChatView.compareTabContent` → `ModelComparisonView()` | ModelComparison is now the Compare *tab*, not a top-level mode. **Built (#4001).** |
| Save as Workspace | `ChatView.chatBottomBar` → `WorkspaceStore.save` (#3533) | Chat is ephemeral until saved as a node. **Built.** |
| Search-as-a-tool, visible | `RetrievalInfo` (`Models/SidebarChatTypes.swift:77`), rendered `MessageCard.swift:24` | Per-message "Searched library · N documents · M claims." **Built.** This is the read-only ancestor of the ToolCall spine. |
| Knowledge tab | `ChatView.knowledgeTabContent` | `ContentUnavailableView` **placeholder.** |
| Physical fold | `#4001` (`1beb91a5f`) | `Views/Research/` + `Views/ModelComparison/` → `Views/Chat/`. **Done.** |

**Engine (from `agent_chat_as_user.md`, memory, #2571 audit) — NOT built:**

- `fichero-engine/.../actions/chat_tools.py` already generates one LLM tool per
  registry action (`action_tools()` / `dispatch_tool_call()`, `actor="chat"`); its
  own note says wiring into `/api/chat` is "a small safe edit." Today `/api/chat`
  is **single-shot RAG** (`llm.invoke(messages)`), no tool loop.
- MCP already does "model is a user" and audited (`mcp_server.py::_agent_client` →
  `/api/actions/invoke`). But research tool clicks (`/api/research/tools/*`)
  **bypass** the audited action layer — same capability, two provenance regimes
  (violates #1848). Normalizing these is engine work.

**The gaps (front-end):**

1. **No `ToolCall` product spine in Swift.** `Models/Trace.swift` is a *debug*
   trace (llm/chain/tool/retriever/agent — timing/cost/IO); it is **not** the
   product spine. `ChatMessage` (`SidebarChatTypes.swift:47`) has `sources` +
   `retrieval` but **no `tool_calls`**. Nothing renders an audited action.
2. **Three provenance shapes, no ledger.** `DocumentSource` (chat,
   `SidebarChatTypes.swift:110`), `ResearchSource` (research project,
   `ResearchModels.swift:117`), and KG usage inside `RetrievalInfo`
   (`kgClaimsUsed`/`kgEntitiesUsed`) are three separate ideas of "where this came
   from." No unified read-only ledger.
3. **No Plan tab on the chat surface.** `ResearchTasksPane` exists but is reachable
   only inside `ResearchWorkspaceView`'s 3-pane. The continuum ("open Plan
   promotes chat → research") has no seam on `ChatView`.

---

## 3. The shared spine (target)

**`ToolCall`** — one record every kind of agent action collapses onto:

```
ToolCall {
  id
  workspace_id
  message_id?        // when it came from a chat turn
  task_id?           // when it came from a plan task
  action_name        // canonical registry action
  params
  actor              // a real user account (human or model-user) — #1847
  audit_id?          // REQUIRED for mutating calls — ties to ActionAudit
  status             // pending / running / ok / error
}
```

A research **Step**, a chat **tool call**, an **MCP mutation**, and a compare
**node** are all `ToolCall`s; mutating ones **must** carry `audit_id`. `RetrievalInfo`
is the already-shipped read-only special case (a search tool with no mutation).

**Source ledger** — unify `DocumentSource` + `ResearchSource` + KG usage into one
read-only provenance list: *what the conversation actually used*, with a kind
(document / research-source / knowledge) and a link back to the node. Distinct
from the *pinned scope* (what the user gave the chat, edited in the Sources tab
via `ChatInspector`). Pinned = input; ledger = what got cited.

UX bars this must honour: **AI = instrument not interlocutor** (surface facts +
provenance, no pretend-human — the ledger and ToolCallCard *show what happened*,
they don't narrate); **Every Frame Perfect** (no placeholder flashes, explainable
frames); **dead-simple UX** (tabs, not a pile of toggles); ToolCall = the shared
unit.

---

## 4. Migration — steps 1–3 engine (reorg-gated), 4–6 Swift

From the memory plan. **Disjoint by layer**, so the Swift subset is parallel-safe.

| # | Step | Layer | This lane? |
|---|---|---|---|
| 1 | Register research tools as audited registry actions (old routes delegate) | **engine** | ✗ reorg-gated |
| 2 | Agentic `/api/chat`: wire `chat_tools.py` behind default-off flag; reads first, writes gated by `orchestration.py` policy; response gains `tool_calls[]`; OpenAPI tri-copy | **engine** | ✗ reorg-gated |
| 3a | **`ToolCallCard` + `ToolCall` Swift model** (renders `tool_calls[]` when the engine emits them; decodes as optional, nil today) | **Swift** | ✅ **now** |
| 3b | **Sources ledger UI** (unify the three provenance shapes, read-only) | **Swift** | ✅ **now** |
| 4 | **Plan tab** = surface `ResearchTasksPane` on `ChatView` (the continuum seam) | **Swift** | ✅ **now** |
| 5 | Fill Knowledge tab + SPARQL console (second host of `KGQueryStore`, keep `OntologyBrowser` copy) | **Swift** | ~ later (needs KG store wiring) |
| 6 | Collapse `SidebarMode.research`, remove ⌘8 + the `ContentView+Navigation` research intercept | **Swift, sidebar-owned** | ✗ DEFER — `sidebar` lane |
| 7 | (cosmetic) folder `Chat/` → `Research/` git-mv | Swift | ✗ later, needs coordination |

### Actionable now (this lane)

1. **`ToolCall` model + `ToolCallCard`.** Add `ToolCall` (snake_case CodingKeys,
   ready for `tool_calls[]`). Add `toolCalls: [ToolCall]?` to `ChatMessage`
   (optional, defaults nil — decodes cleanly against today's engine, exactly like
   `sources`/`retrieval`). Render each in `MessageBubble` as a compact,
   instrument-style card: action · status · actor · params disclosure · audit
   badge when present. View-model unit-testable; no engine dependency.
2. **Source ledger.** A `SourceLedgerEntry` unifying the three shapes, a builder
   `SourceLedgerEntry.ledger(for: Conversation)` that derives cited sources from
   `message.sources` (dedup by document, kind = document/knowledge), and a
   read-only `SourcesLedgerView`. Surface it in the Sources tab as a **Cited**
   section beneath the pinned-scope editor (`ChatInspector`), so the tab reads:
   *pinned = what you gave it · cited = what it used.* Builder is pure → one test.
3. **Plan tab.** Add `.plan` to `ChatSurfaceTab`. `ChatView` gains an optional
   `researchProject: ResearchProject? = nil` (all three call sites keep
   compiling). Plan tab renders `ResearchTasksPane(project:)` when a project is
   present, else a `ContentUnavailableView` that names the continuum ("Save this
   chat as a workspace to plan tasks"). `ResearchChatPane` passes its project
   through, so the workspace's embedded chat lights the Plan tab up.

### Explicitly deferred / flagged for coordination

- Steps 1, 2 (engine `chat_tools.py` wiring, `/api/chat` tool loop, audited
  research actions, OpenAPI tri-copy) — **engine lane, post-reorg.** The Swift
  ToolCall model is built to decode `tool_calls[]` the day the engine emits it.
- Step 6 (SidebarMode.research collapse, ⌘8 removal, node-kind routing / #2446
  "modes → node kinds") — **sidebar lane + engine.** Do not touch the sidebar
  tree, `SidebarMode`, or `ContentView+Navigation`'s research intercept here.
- Chat-panel *zone* work (content-split column, inspector→Plan repurpose, bottom
  multi-agent area, detach-to-window) — **shell lane / larger; needs the
  `ContentView` type-checker-budget discipline (`librarywindow-body` rule).** Not
  in this parallel-safe subset.
- Global read-only default nodes + `Duplicate` — **engine** (node scope + server
  enforcement + idempotent seeding).

### Open questions (Daniel)

- Write-policy default: approval-always vs `orchestration.py` policy (respect the
  *hold-security-contract* rule — don't flip a shipped auth assertion).
- `ResearchProject` link-don't-migrate (Marshall data is real — never nuke).
- Streaming SSE for the tool loop (copy `WorkflowStreamService`).
- Which providers get `tools_enabled`; the surface icon.
