# Agent / Research / Chat surface — survey (2026-07-29)

Lane: finish + switch on the agent/research/chat system (#2056, #2067,
agentic-surface consolidation). Plus #4308 (new chat/workspace invisible in
sidebar) added mid-task.

## What already exists (more than expected)

### Server (`fichero-server/src/fichero_server`)
- `actions/chat_tools.py` — COMPLETE generator + dispatcher: every registry
  action becomes a LiteLLM/OpenAI tool (`action_tools`), dispatch goes through
  the audited `registry.invoke` choke point (`dispatch_tool_call`), name
  sanitisation + reverse resolution included.
- `api/routes/system/chat.py` — the chat_tools loop is ALREADY WIRED
  (`_run_chat_tools_loop`, #1847/#3): bounded (4 iterations), READS-ONLY
  (mutating tool calls recorded as `status=error`, never invoked), each read
  dispatched through the audited action layer with `audit_id` returned in
  `tool_calls[]` on `ChatResponse`. **But it is default-OFF behind the
  `FICHERO_CHAT_TOOLS` env flag — this is the "built but never enabled" gap.**
- Tests exist: `tests/unit/actions/test_chat_tools_loop.py` (flag off/on,
  read dispatched + audited, mutation denied + never invoked).
- Agent workspaces (#3533): `/api/chat/workspaces` CRUD over workspace nodes
  (`workspace_kind=agent`), plus workspace.* actions (add_source, surface_claim,
  add_note) — all audited/undoable.
- `conversation.update/duplicate/delete/restore` actions registered. **There is
  NO conversation.create action and NO plain create endpoint** — a conversation
  only comes into existence as a side effect of a successful LLM chat turn.
- Research routes (`api/routes/research*`), `mcp/research_tools.py`,
  langchain via `fichero_server.llm` (lazy-imported, #3950/#3976).

### Swift (`fichero/fichero`)
- `SidebarMode` has `.chat` (⌘3) and `.research` (⌘8); both feature-flagged
  `beta` tier, visible in dev builds and gated by FeatureManager toggles.
- Unification is FURTHER ALONG than the epic implies: `ResearchChatPane`
  embeds the shared `ChatView` (#3532/#3540 — "one chat interface"), scoped to
  `/research/{project_id}` folder paths. ModelComparison (compare surface)
  lives inside the same Chat views tree.
- The ToolCall product spine exists end-to-end in the UI: `Models/ToolCall.swift`
  (snake_case codable mirror of the server model), `ToolCallCard`, and
  `MessageCard` already renders `message.toolCalls`. `SidebarChatTypes.ChatMessage`
  carries `toolCalls`.
- **Gap:** `ChatService.convertToChatAPIResponse` DROPS `tool_calls` from the
  server response (`ChatAPIResponse` has no field for it), and
  `ChatView+Extensions.sendMessage` builds the assistant `ChatMessage` without
  toolCalls — so the ToolCallCard UI can never light up even with the loop on.
  The client openapi.json already contains `ChatResponse.tool_calls` + `ToolCall`.

## #4308 diagnosis (new chat/workspace invisible in sidebar)
- `SidebarCreationHandlers.createNewChat()` creates a chat by POSTing an
  actual LLM turn (`chat(message: "Hello")`). If no provider/API key is
  configured, or retrieval fails (502), or the LLM errors, the create fails
  and is swallowed by a `catch` that only logs → **nothing reaches the server,
  nothing appears in the sidebar**. Server-side there is no way to create a
  conversation without a successful LLM roundtrip.
- Sidebar chat rows are built from `conversationService.conversations`
  (`SidebarItemBuilder.buildChatHierarchy`) with observers — the refresh path
  is fine once a conversation actually exists (append + rebuildCaches).
- Workspace half: agent workspaces persist server-side (document.create), but
  the sidebar has no workspace section (dangling comment in SidebarView, #3533
  store never injected) — workspaces are reachable from the Chat surface, not
  the sidebar tree.

## Completion plan (minimal path)
1. **Server: switch the agent loop ON by default.** `_chat_tools_enabled()`
   becomes default-true with `FICHERO_CHAT_TOOLS=0` as the kill switch; add a
   graceful fallback when the bound model/provider cannot `bind_tools`
   (fall back to single-shot rather than 500). Update/extend loop tests.
2. **Server: `conversation.create` action + `POST /api/chat/conversations`**
   (title/folder_path, no LLM required), audited + undoable (invert → delete).
   This is the server half of #4308. Regression tests: route persists, appears
   in list, audit row exists, no LLM needed.
3. **Regenerate OpenAPI** (`fichero-server/scripts/sync_openapi_schema.sh`),
   check diff is only the new endpoint/schema, commit.
4. **Swift: tool-call visibility.** Add `toolCalls` to `ChatAPIResponse`, map
   generated `Components.Schemas.ToolCall` → app `ToolCall` in `ChatService`,
   attach to the assistant `ChatMessage` in `sendMessage` → existing
   `ToolCallCard` UI lights up. Additive only.
5. **Swift: fix #4308 client half.** `createNewChat()` calls the new create
   endpoint instead of the "Hello" LLM roundtrip — instant, offline-safe,
   appears in sidebar immediately (append + rebuildCaches + select unchanged).
6. Tests with each slice (pytest route tests with scripted fake LLM; Swift
   codable/builder tests where they run without a build).

## Deliberately NOT done here (flagged as remaining)
- Full mode consolidation (retiring `.chat` as a separate sidebar mode so
  Research is the ONE surface) — the shared-ChatView unification means both
  modes already render the same surface; removing the `.chat` mode touches
  ViewMenuCommands/FicheroApp/mode persistence and needs the manager's build
  gate + a design decision on where non-project chats live. Noted for follow-up.
- Streaming (SSE token streaming for chat) — the response path is
  request/response today; streaming is an additive endpoint change that should
  ride on the existing SSE change-stream patterns, separate slice.
- Sidebar workspace section (lane boundary: sidebar row/drop/prefetch code).
