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

## Next (Swift-parallel-safe subset only)
- [ ] Step 3a — `ToolCall` model + `ToolCallCard`; `toolCalls: [ToolCall]?` on `ChatMessage`; render in `MessageBubble`.
- [ ] Step 3b — `SourceLedgerEntry` + `SourcesLedgerView`; surface as a "Cited" section in the Sources tab. + builder test.
- [ ] Step 4 — `.plan` tab on `ChatSurfaceTab`; `ChatView` optional `researchProject`; `ResearchTasksPane` when present, continuum unavailable-state otherwise; `ResearchChatPane` passes project through.

## Deferred / flagged for coordination
- Engine steps 1–2 (`chat_tools.py` → `/api/chat` tool loop, audited research actions, OpenAPI tri-copy) — engine lane, post-reorg. Swift `ToolCall` decodes `tool_calls[]` when engine emits it.
- Step 6 (collapse `SidebarMode.research`, remove ⌘8, node-kind routing / #2446) — sidebar lane + engine. NOT this lane.
- Chat-panel zone work (content-split chat column, inspector→Plan, bottom multi-agent, detach-to-window) — shell lane, larger. Not in the parallel-safe subset.

## Decisions for Daniel
- (none blocking yet). Open questions carried in the doc §4: write-policy default, ResearchProject link-don't-migrate, streaming SSE for the tool loop, providers with tools_enabled, surface icon.

## Build-verify needed (manager owns the gate — no `xcodebuild` here)
- After the three Swift steps land, needs a `build-for-testing` gate + the new view-model test target run.
