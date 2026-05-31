# Reality Check — Chat Milestone (Open Issues)
Date: 2026-05-31  
Auditor: claude-sonnet-4-6 (read-only, no build/run)

---

## Summary

| # | Title | Status | Verdict |
|---|-------|--------|---------|
| 1268 | Model-comparison interface — abstract view + per-node testing | PARTIAL | Abstract UI exists; per-node affordance missing |
| 1156 | Interactive RAG / graph-RAG chat agent | PARTIAL | RAG works; graph-RAG KG traversal absent |
| 487 | [Release Gate] 0.0.9 — Wire: Chat v2 (Model Comparison) | PARTIAL | Comparison UI + service wired; search-history + extract-text gated off by default |
| 486 | [Release Gate] 0.0.8 — Wire: Chat v1 | PARTIAL | Core chat functional; citation navigation (click → source doc) unimplemented |
| 247 | Promote Chat to release if ready | OPEN | Gate not satisfied; chat feature flag default=false |
| 246 | Add Chat stability and QA coverage | OPEN | No dedicated chat unit/integration tests found |
| 245 | Gate Chat cleanly when off | DONE | `isChatEnabled` flag guards sidebar mode icon and nav routing |
| 244 | Promote Chat from off to beta | OPEN | `chatEnabledInternal` defaults to `false` in FeatureManager; not yet promoted |

---

## Detailed Evidence

### #245 — Gate Chat cleanly when off — DONE
- `FeatureManager.swift:52` — `@AppStorage("fichero.features.chat") private var chatEnabledInternal: Bool = false`
- `SidebarModeBar.swift:39` — `if featureManager.isChatEnabled { ... mode: .chat ... }`
- `ContentView+Navigation.swift:81-87` — `case .chat(let conversation):` renders `ChatView`
- The flag correctly hides the sidebar icon and prevents nav routing when off.

### #1156 — Interactive RAG / graph-RAG chat agent — PARTIAL
Evidence chat works (vector RAG):
- `chat.py:330-359` — hybrid semantic search via `db.search(search_type="hybrid")`
- `ChatServiceGenerated.swift` — fully wired to `POST /api/chat` via OpenAPI client
- `ChatView+Extensions.swift:88-138` — `sendMessage()` calls `chatService.chat(...)`, appends sources to messages

Missing — graph-RAG (KG traversal):
- `chat.py` contains zero references to entities, claims, relationships, KG, or knowledge-graph traversal
- The `/api/kg/graph/traverse/{entity_id}` endpoint exists (`kg_graph.py:206`) but is never called from `chat.py`
- Issue AC explicitly requires: "Agent uses both vector search AND KG traversal (entity/claim relationships)" — second half unmet

Missing — clickable citation navigation:
- `MessageBubble.swift:44-66` — sources rendered as plain `Text(source.documentName)` with no `Button` or `NavigationLink`; tapping a citation does not navigate to the source document/page
- Issue AC: "Agent responses include clickable citations that navigate to the source document/page" — not met

Missing — SSE/streaming:
- Issue design notes specify `POST /api/chat` as a streaming SSE endpoint; `chat.py` returns a plain synchronous `ChatResponse`, no `StreamingResponse` or `EventSourceResponse`

Conversation history persistence:
- `db.save(conv)` in `chat.py:393` — backend persists to DuckDB. `ConversationServiceGenerated.swift` loads/lists conversations. History persistence is implemented.

System prompt configurability:
- `chat.py:247-256` — system prompt is hardcoded in `_build_rag_prompt()`: "You are a helpful assistant that answers questions about documents in a personal archive." Not user-editable via settings. Issue AC requires "System prompt is configurable via settings (not hardcoded)" — not met.

### #486 — Release Gate 0.0.8 Wire: Chat v1 — PARTIAL
Checklist items satisfied:
- Chat panel opens: yes (ChatView renders in content area when `.chat` mode)
- AI responds: yes (RAG pipeline functional)
- Chat history persists: yes (DuckDB + ConversationServiceGenerated)
- Separate conversation per document: yes (document_ids scoping in ChatRequest)

Checklist items NOT satisfied:
- "The response references actual content from the document" — only satisfied when `page_content` field is populated; `chat.py:342` falls back to `_read_file_content()` for text files only, binary/PDF content requires prior workflow extraction
- Clickable citation navigation: missing (see #1156 above)
- "Select a document → chat icon in toolbar becomes active": `ChatViewToolbar` shows document count but the toolbar icon is always present when chat mode is on — not dynamically activated by document selection

### #487 — Release Gate 0.0.9 Wire: Chat v2 (Model Comparison) — PARTIAL
Evidence implemented:
- `ModelComparisonView.swift` + `ModelComparisonView+Sidebar.swift` — full abstract comparison UI
- `ModelComparisonService.swift` — calls `/api/model-comparison/compare`, `/compare-vision`, `/compare-tool`, `/history`, `/presets`, `/models`
- `model_comparison.py` backend route registered
- `ContentView+Navigation.swift:89-94` — `.comparison` mode routes to `ModelComparisonView()` or `ComparisonDetailView`
- `ComparisonDetailView.swift` — detail view renders per-comparison results

Checklist items NOT satisfied:
- "Click 'Compare Models' → model picker opens" inside the Chat view specifically: the Compare Models button/flow in ChatView is not present. `ModelComparisonView` is a separate navigation mode (`.comparison`), not an in-chat affordance
- "Search conversation history → past conversations filtered by keyword": `list_conversations` endpoint only filters by `folder_path`, no search/keyword param
- "Extract text from a message → plain text copied to clipboard": `ChatInspector+Actions.swift` may have this; requires verification. The backend endpoint `POST /api/chat/extract-text` exists in `chat.py:645` but extracts document text (not message text)

### #1268 — Model-comparison interface — abstract view + per-node testing — PARTIAL
Evidence implemented:
- Abstract comparison panel fully exists: `ModelComparisonView`, `ComparisonResultView`, `ModelPickerSheet`, `PresetPickerSheet`, `ModelResultCard`
- Service wired to backend for text, vision, and tool comparison

Missing — per-node "Compare models…" affordance:
- `WorkflowEditor.swift`, `WorkflowNodeView.swift`, `NodeProviderModelSelector.swift` — none contain a "Compare models" button or any hook to `ModelComparisonService`
- Issue specifies: "a per-node 'Compare models…' affordance in the node editor that opens the side-by-side, with an 'apply this model to the node' action" — not implemented

### #244 — Promote Chat from off to beta — OPEN
- `FeatureManager.swift:196` — `chatEnabledInternal = false` in `resetToV001()`
- Chat is not promoted to beta; the flag is explicitly reset to false in the release profile

### #246 — Add Chat stability and QA coverage — OPEN
- `fichero-engine/tests/unit/` — no chat-specific test files found under standard paths
- Issue requires: "Define and satisfy the testing and QA gate for Chat beta" — not verifiable as done

### #247 — Promote Chat to release if ready — OPEN
- Dependent on #244, #246, and AC from #486/#1156; none fully satisfied

---

## Safe to Close Now

**#245** — `Gate Chat cleanly when off` — flag guards are correctly implemented everywhere. The feature is invisible to users when the flag is off. Can be closed.

## Needs Work (priority order)

1. **#1156 / #486** — Graph-RAG KG traversal: wire `chat.py` to call `/api/kg/graph/traverse` for entity relationship context; add entity/claim lookup to retrieval path
2. **#1156 / #486** — Clickable citations: `MessageBubble` sources must become tappable with navigation action to source document
3. **#1156 / #486** — System prompt configurability: move hardcoded prompt to user settings
4. **#487** — Conversation history keyword search: add `search` query param to `GET /api/chat/conversations`
5. **#1268** — Per-node compare affordance: add "Compare models…" button to `WorkflowNodeView` that opens `ModelComparisonView` pre-scoped to that node's tool + inputs
6. **#244** — Flip `chatEnabledInternal` default to `true` in `resetToV001()` once ACs are met
7. **#246** — Write chat unit + integration tests
8. **#247** — Release gate: blocked until all above complete
