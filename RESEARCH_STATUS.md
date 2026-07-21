# Research lane — status

Lane: frontend (SwiftUI) agentic surface consolidation. Worktree
`~/code/fichero-worktrees/research`, branch `lane/research-agent-ux`.
Do NOT push (manager gates). Do NOT touch `fichero-engine/` or the sidebar tree.

## Done
- **Phase 1 — plan reconstructed + consolidated.** Authoritative source =
  memory `agentic-surface-consolidation-plan.md` (2026-07-19/20 fabel reviews +
  Daniel decisions). Cross-checked against the retired `research_agent_search_audit_2571.md`
  (recovered via `git show 7d714eab3:...`), `2026-07-12-surface-consistency-design.md`,
  `agent_chat_as_user.md`, and the #4001 fold (`1beb91a5f`). Written to
  `docs/design/agentic-surface-consolidation-fabel-review.md` (code-grounded:
  current state, gaps, migration steps 1–3 engine / 4–6 Swift, deferrals).

## Done (Swift-parallel-safe subset)
- [x] Step 3a — `ToolCall` model + `ToolCallCard`; `toolCalls: [ToolCall]?` on `ChatMessage` (snake_case, optional); rendered in `MessageBubble`. Tests: back-compat decode + display helpers. (`e3e2ffede`)
- [x] Step 3b — `SourceLedgerEntry` + `SourcesLedgerView`; "Cited" ledger under the Sources tab (pinned=input / cited=used). Builder test: dedup/empty/research order. (`f1873e536`)
- [x] Step 4 — `.plan` tab on `ChatSurfaceTab`; `ChatView` optional `researchProject`; `ResearchTasksPane` when present, continuum "Save as Workspace" unavailable-state otherwise; `ResearchChatPane` threads its project. Tab-contract test.

Subset complete. All SourceKit diagnostics during this work were whole-module
false negatives (the worktree index isn't built — even existing types like
`Conversation`/`ChatMessage` reported "not found"); real verification is the
manager's build gate.

## Delegated to the manager (chat-panel zone work — Option A)
Filed as worker-sized lanes under milestone **Agent View - Researcher - UX**
(Daniel: "plan and delegate"). Each carries the memory decisions + the #2033
hazard + the `librarywindow-body` type-checker discipline:
- **#4041** zone A — chat column inside the content zone (`HSplitView`, NOT a 2nd right panel)
- **#4042** zone B — inspector → contextual Plan/detail surface (node PM surface; coordinate with sidebar/node lane)
- **#4043** zone C — agent-driven visible browser renders in the Reader (ties #2275; needs WebKit-MCP engine)
- **#4044** zone D — bottom multi-agent activity area (new chrome; feeds off the ToolCall spine)
- **#4045** zone E — detach chat to window + workspace-window save/restore

## In this lane next (parallel-safe, no zone collision)
- [ ] Knowledge tab (migration step 5) — conversation-scoped entities/claims; 2nd `KGQueryStore` host.
- [ ] Polish — ledger source-navigation (click a cited doc → open), ToolCallCard running/error states.

## Deferred / flagged for coordination
- Engine steps 1–2 (`chat_tools.py` → `/api/chat` tool loop, audited research actions, OpenAPI tri-copy) — engine lane, post-reorg. Swift `ToolCall` decodes `tool_calls[]` when engine emits it.
- Step 6 (collapse `SidebarMode.research`, remove ⌘8, node-kind routing / #2446) — sidebar lane + engine. NOT this lane.
- Chat-panel zone work (content-split chat column, inspector→Plan, bottom multi-agent, detach-to-window) — shell lane, larger. Not in the parallel-safe subset.

## Decisions for Daniel
- (none blocking yet). Open questions carried in the doc §4: write-policy default, ResearchProject link-don't-migrate, streaming SSE for the tool loop, providers with tools_enabled, surface icon.

## Build-verify needed (manager owns the gate — no `xcodebuild` here)
- After the three Swift steps land, needs a `build-for-testing` gate + the new view-model test target run.
