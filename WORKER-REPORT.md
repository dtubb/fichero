
## #2571 — audit Researcher/Agent/Search surfaces (SwiftUI App Structure & Naming)
Done by f_fichero_claude_swiftui (2026-06-28).

- AUDIT delivered: `docs/architecture/swiftui/research_agent_search_audit_2571.md` (commit 7d714eab, authored Claude). Findings also posted to issue #2571.
- Finding: not three peer surfaces. Search = retrieval primitive (`/api/search`); Chat = conversational spine (`/api/chat`); Research = Chat + workspace (`ResearchChatPane` re-instantiates `ChatView`; `/api/research`); Agent = no SwiftUI surface (only `/api/agent-memory` + Trace.agent + Workflow "Agents" tab; EPIC #2067 is the target).
- `research_agents.py` is a 19-line aggregator with no agent logic — backend rename candidate (#2565).
- Proposed staged fold (S0 audit → S1 naming → S2 search-as-tool → S3 fold Research → S4 Agent). No structural code shipped: collapse touches 3 SHIPPED sidebar modes + KB shortcuts + `@SceneStorage`; canonical name owned by #104 vocabulary table. iterate-never-replace + "don't break shipped surfaces in one step."
- BLOCKED on #104 (naming) before Stage 1.
- Docs-only; no build gate (no .swift / no pbxproj). NOT pushed.
