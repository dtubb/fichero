(AI generated. Not reviewed.)

# Researcher / Agent / Search Surface Audit (#2571)

Status: audit captured for the *SwiftUI App Structure & Naming* milestone. No
behavior changed by this document. The structural collapse it proposes is
**design-gated** (pairs with the #104 vocabulary table and the #2565 API-naming
pass) and must be staged — not done in one step.

## TL;DR

There are **not** three peer surfaces. There is one spine and two satellites:

- **Search** — a *retrieval primitive*. Standalone sidebar mode, but the backend
  already uses the same retrieval inside Chat (RAG).
- **Chat** — the *conversational spine*. RAG conversation over the library.
- **Research** — *Chat + a project workspace*. It already re-uses `ChatView`
  verbatim; it adds a web browser pane and a tasks/notes/sources pane.
- **Agent** — **no dedicated SwiftUI surface exists.** "Agent" today is
  `agent-memory` (notes CRUD), a `Trace.agent` case, and a Workflow-inspector
  "Agents" tab. The in-app Agent (EPIC #2067, "Researcher → Agent") is the
  *target*, not a current surface.

So the conceptual model the issue suspected is largely already true in code:
**Research embeds Chat; Search is the tool Chat retrieves with.** Consolidation
is mostly *naming + folding the Research workspace into the Chat spine*, plus
deciding what the canonical surface is called.

## Front-end map

`SidebarMode` (`App/ViewSettings.swift`) — relevant cases:

| Mode | Content view (`ContentView+Navigation.swift`) | Store | Service | Endpoint family |
|---|---|---|---|---|
| `.search` | `SearchView` | `SearchStore` | `SearchServiceGenerated` | `/api/search` |
| `.chat` | `ChatView` | — (per-view state) | `ChatServiceGenerated`, `ConversationServiceGenerated` | `/api/chat` |
| `.research` | `ResearchProjectListView` → `ResearchWorkspaceView` | `ResearchStore` | `ResearchService` | `/api/research` |

`ResearchWorkspaceView` is a 3-pane layout: **CHAT \| BROWSER \| TASKS**.

- `ResearchChatPane` → **re-instantiates `ChatView`** (already shared, no fork).
- `ResearchBrowserPane` → web browser (unique to Research).
- `ResearchTasksPane` → tasks / notes / sources (unique to Research).

There is **no** `AgentStore` / `AgentView` / `.agent` sidebar mode. "Agent" is not
a front-end surface today.

Saved searches: `SavedSearchService` + `RecentSearchesStore` back the `.search`
mode's saved-search list. Chat conversations are listed via
`ConversationServiceGenerated`. Research projects via `ResearchStore`. Three
parallel "list of saved things in the sidebar" patterns.

## Back-end map

Router mounts (`api/main.py`). All are **shipped core** for 0.0.2 — every former
dev-tier router was promoted to `_CORE` (main.py ~line 1408), so none of these is
dev-gated anymore.

| Router | Mount | Notes |
|---|---|---|
| `chat.py` | `/api/chat` | `POST ""` (RAG chat, builds context docs + system prompt), conversations CRUD/reorder/duplicate, providers, extract-text. The RAG retrieval here *is* search-as-a-tool. |
| `search.py` | `/api/search` | `POST ""` (search), stats, keywords, reindex, embed, saved-search CRUD/duplicate. |
| `search_explain.py` | `/api` (`search-explanation`) | explain/why-ranked. |
| `research_agents.py` | `/api/research` | **Aggregator only** (19 lines). Includes `research_crud` + `research_notes` + `research_tools`. *Despite the name, contains no "agent" — projects/plans/tasks/notes/sources/tools CRUD.* |
| `agent_memory.py` | `/api/agent-memory` | Agent notes CRUD. The only literal "agent" endpoint family; not wired to a sidebar surface. |
| `kg_search.py`, `kg_claim_search.py` | `/api` (`knowledge-graph`) | Entity/claim search — belong to the Knowledge Graph surface, **out of scope** for this collapse. |

### Redundancy verdict

- **Genuinely distinct:** `research_tools` (web browser save, research-specific
  tools), `search` reindex/embed/stats (index management), `chat` RAG.
- **Misleading naming:** `research_agents.py` is a router aggregator with no
  agent logic — a rename candidate (backend lane, #2565).
- **Conceptually one thing:** Chat RAG retrieval and Search are the *same*
  retrieval operation exposed twice (once as a primitive UI, once as an implicit
  tool inside chat). This is the core overlap.
- **Not redundant, just adjacent:** `agent-memory` is the persistence the future
  Agent surface will need; keep it.

## Proposed consolidated model (front-end-first)

One conversational surface ("**Agent**" per EPIC #2067 / "Researcher → Agent",
final name set by the #104 vocabulary table) that:

1. **is** the Chat spine (`ChatView` stays the implementation),
2. **uses Search as a tool** (backend chat already retrieves; make the tool
   explicit/visible),
3. **subsumes the Research workspace** as an optional *project-scoped* mode
   (browser + tasks/notes panes attach to a conversation that has a project).

Search remains available as a standalone retrieval mode (power-user / index
management lives there: reindex, stats, keyword cloud) — it is the primitive, not
a peer conversational surface.

## Staged migration (do NOT collapse in one step)

- **Stage 0 — this document.** No behavior change. ✅
- **Stage 1 — naming (design-gated, #104).** Decide the canonical name for the
  conversational surface and the workspace. Update `SidebarMode` labels + KB
  shortcuts. No structural code move yet. *Owner: Daniel + #104.*
- **Stage 2 — search-as-tool, visible in Chat.** Surface the retrieval the chat
  backend already performs as an explicit affordance in `ChatView` (it exists in
  `chat.py`'s `_build_rag_user_prompt` / context docs path). Additive; reversible.
- **Stage 3 — fold Research into the spine.** `ResearchWorkspaceView` already
  hosts `ChatView`; invert ownership so a Chat conversation can *gain* the
  browser/tasks/notes panes when it belongs to a research project. Retire the
  separate `.research` content path once parity is proven. Requires
  `@SceneStorage` sidebar-mode persistence migration — must not orphan existing
  windows.
- **Stage 4 — Agent.** Build the EPIC #2067 agent behavior (tools = action
  registry #1848, memory = `/api/agent-memory`) on the unified surface.

## Why nothing structural ships in this pass

The collapse changes a **shipped** surface (all three modes are in 0.0.2),
renumbers keyboard shortcuts, and migrates per-window `@SceneStorage` state. The
canonical naming is owned by the #104 vocabulary table, not this audit. Per
project rule *iterate-never-replace* and the issue's own "don't break the shipped
surfaces in one step," the safe deliverable now is this map + staged plan. The
existing `ResearchChatPane` → `ChatView` reuse means the eventual fold is an
ownership inversion, not a rewrite.
