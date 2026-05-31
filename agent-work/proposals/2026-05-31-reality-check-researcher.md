# Reality Check — Researcher Milestone (Open Issues)
Date: 2026-05-31  
Auditor: claude-sonnet-4-6 (read-only, no build/run)

---

## Summary

| # | Title | Status | Verdict |
|---|-------|--------|---------|
| 1335 | Researcher: next-phase agentic capabilities (parent) | OPEN | Design only; no child issues yet, marked needs-design |
| 1157 | Research agents: project tracking + AI-controlled browser for source discovery | PARTIAL | CRUD + browser + web-save wired; AI-controlled browser (agent drives navigation) absent |
| 514 | [Release Gate] 0.7.1 — Wire: Research Agents | OPEN | Agentic gather/findings loop not implemented |
| 513 | [Release Gate] 0.7.0 — Wire: Agents | OPEN | Agents mode / autonomous workflow agent loop not implemented |

---

## Detailed Evidence

### Shared Retrieval Path Note (graph-RAG)
The `ResearchChatPane` re-uses `ChatView` directly:
- `ResearchChatPane.swift:13-19` — `ChatView(conversation: nil, selectedDocuments: $chatSelectedDocuments, ...)`
- Therefore research chat uses the **same** `POST /api/chat` → hybrid vector search pipeline as the main Chat window
- Graph-RAG KG traversal is absent in both (see Chat reality check); this is a single shared gap, not a duplicate implementation

### #1335 — Researcher: next-phase agentic capabilities (parent) — OPEN
- Body states "A1–A10 done; next phase: agentic actions (browse → save → annotate → file under workspace), citation discovery, source verification, summarisation"
- Labelled `needs-design` and `tier:frontier` — explicitly not ready for implementation
- No child issues exist yet
- Status: design placeholder, should remain open

### #1157 — Research agents: project tracking + AI-controlled browser — PARTIAL

Evidence implemented:
- **Project/Plan/Task/Step CRUD**: `research_crud.py` fully implements `POST/GET/PATCH /api/research/projects`, `/plans`, `/tasks`, `/steps`, `/sources`
- **Notes and Checklists**: `research_notes.py` implements `/api/research/notes`, `/api/research/checklists`
- **Web search tool**: `research_tools.py` — `POST /api/research/tools/web-search` (httpx with SSRF guard)
- **Browser navigate**: `research_tools.py` — `POST /api/research/tools/browser-navigate` (returns page text via httpx)
- **Browser save (import to library)**: `research_tools.py` — `POST /api/research/tools/browser-save` — downloads URL, creates `Document` row
- **3-pane workspace**: `ResearchWorkspaceView.swift` — Chat | Browser | Tasks panes, resizable
- **WKWebView browser pane**: `ResearchBrowserPane.swift` — full WKWebView with URL bar + "Save to Library" button; calls `researchService.browserSave()`
- **Tasks pane**: `ResearchTasksPane.swift` — lists tasks + notes, inline note creation
- **Project list**: `ResearchProjectListView.swift` — sidebar list, create/delete projects
- **ResearchService**: fully wired to all CRUD, notes, web-search, browser-save endpoints via `APIClient`
- **Routing**: `ContentView+Navigation.swift:29-39` — research mode renders `ResearchWorkspaceView` when `sidebarMode == .research`
- **Feature flag**: `researchEnabledInternal = true` (default on in `resetToV001()`)
- **Agent-assisted plan creation**: `research_crud.py:234` — `react_agent` called during `POST /api/research/plans` if a `term` is provided; uses `research_web_search` tool to ground the plan

Missing — AI-controlled browser (agent drives WKWebView navigation):
- `ResearchBrowserPane.swift` is purely user-operated; no agentic control path exists
- Issue AC: "AI agent can be dispatched to search configured archives/databases" — the `POST /api/research/tools/browser-navigate` backend endpoint exists, but no Swift UI dispatches it; there is no "dispatch agent" button in the Research workspace
- Issue AC: "Sources discovered by the agent appear in the library as import candidates with approve/reject" — the browser-save flow imports immediately without a staging/approval queue
- Issue AC: "Agent loop: search → filter → extract → present to user → import approved" — no agent loop is wired into the Swift UI; the user manually browses and clicks "Save to Library"

Missing — configurable archives/search parameters in the UI:
- `ResearchTasksPane.swift` shows tasks and notes; no UI for per-project search terms, target languages, or archive selections
- `ResearchProject` model contains `metadata: Dict` but no structured archive/language fields surfaced in the UI

Missing — approve/reject discovered sources:
- Browser save is immediate (no staging queue, no approve/reject step)

### #514 — Release Gate 0.7.1 — Wire: Research Agents — OPEN
Checklist requirements:
- "Open Research panel" — DONE (sidebar mode, `ResearchProjectListView` in sidebar)
- "Type a research question → agent starts" — NOT DONE; there is no "research question" input that dispatches an agent loop. The ResearchChatPane uses standard ChatView (RAG Q&A), not an agentic search loop
- "Agent fetches URLs, summarises sources" — NOT DONE as an autonomous flow; user must manually browse and save
- "Structured findings: claims with source citations" — NOT DONE
- "Findings saved as document artifacts" — NOT DONE (browser-save creates a Document, but not structured findings artifacts)

### #513 — Release Gate 0.7.0 — Wire: Agents — OPEN
Checklist requirements:
- "Agents mode appears in sidebar" — PARTIAL: `AgentsEnabled` flag exists, `AgentConfigurationView` and `AgentSettingsView` exist under `Views/Agents/`, but the agent execution loop UI is not present
- "Configure agent: name, model, goal" — `AgentConfigurationView.swift` and `AgentSettingsView.swift` exist; content needs verification
- "Agent loop runs: steps visible in activity monitor" — No evidence of a running agent loop with step visibility
- "Human-in-the-loop: agent pauses for approval on write actions" — Not implemented

This gate is for a future milestone (0.7.x), far beyond the current 0.0.x track.

---

## Safe to Close Now

**None.** All open issues have meaningful missing implementation.

The closest to closeable is the workspace scaffolding portion of **#1157** (CRUD, 3-pane UI, WKWebView, browser-save — all working), but the AC requires the agentic agent-controlled browser flow which is absent. Conservative recommendation: keep #1157 open.

## Needs Work (priority order)

1. **#1157** — Agent dispatch button in `ResearchWorkspaceView`: add a "Run Research Agent" action that calls `react_agent` with `research_web_search` + `browser_navigate` tools scoped to the project's search terms; surface results as import candidates (not immediate import)
2. **#1157** — Approve/reject staging queue: `POST /api/research/tools/browser-save` should move to a staging state; add Swift UI for approve/reject
3. **#1157** — Per-project search configuration UI: expose `archives`, `target_languages`, `search_terms` fields in the Tasks pane or a project settings sheet
4. **#1335** — Design child issues for next-phase agentic capabilities before any code work
5. **#514** — Research agent findings loop: "research question → agent fetches → structured findings report" pipeline (backend + Swift UI)
6. **#513** — Autonomous workflow agent loop: out-of-scope for current 0.0.x milestone, defer to 0.7.x track

---

## Shared Path Verification

The **graph-RAG shared engine** question: Chat and Researcher both use the same `POST /api/chat` retrieval path (Researcher via `ResearchChatPane` → `ChatView`). The vector/hybrid search layer is shared. Graph-RAG (KG traversal) is absent in both. Fixing it in `chat.py` benefits both surfaces automatically since they share a single code path.
