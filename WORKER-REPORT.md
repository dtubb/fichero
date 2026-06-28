
## #2571 — audit Researcher/Agent/Search surfaces (SwiftUI App Structure & Naming)
Done by f_fichero_claude_swiftui (2026-06-28).

- AUDIT delivered: `docs/architecture/swiftui/research_agent_search_audit_2571.md` (commit 7d714eab, authored Claude). Findings also posted to issue #2571.
- Finding: not three peer surfaces. Search = retrieval primitive (`/api/search`); Chat = conversational spine (`/api/chat`); Research = Chat + workspace (`ResearchChatPane` re-instantiates `ChatView`; `/api/research`); Agent = no SwiftUI surface (only `/api/agent-memory` + Trace.agent + Workflow "Agents" tab; EPIC #2067 is the target).
- `research_agents.py` is a 19-line aggregator with no agent logic — backend rename candidate (#2565).
- Proposed staged fold (S0 audit → S1 naming → S2 search-as-tool → S3 fold Research → S4 Agent). No structural code shipped: collapse touches 3 SHIPPED sidebar modes + KB shortcuts + `@SceneStorage`; canonical name owned by #104 vocabulary table. iterate-never-replace + "don't break shipped surfaces in one step."
- BLOCKED on #104 (naming) before Stage 1.
- Docs-only; no build gate (no .swift / no pbxproj). NOT pushed.

## #2571 — Stage 2: search-as-a-tool visible in Chat (additive)
Done by f_fichero_claude_swiftui (2026-06-28). Commit 72a7210f, authored Claude.

- Chat backend ALWAYS runs RAG retrieval (GraphAwareRetriever); the response already carried document_count / context_count / kg_claims_used / kg_entities_used but the UI discarded all of it (only `sources` was shown).
- Surfaced it: `ChatAPIResponse` + mapping (`ChatService.swift`, `ChatServiceGenerated.swift`) → `RetrievalInfo` model + `ChatMessage.retrieval` (`SidebarChatTypes.swift`) → captured in `ChatView+Extensions.swift` → rendered as a "Searched library · N documents · M claims" line in `MessageBubble` (`MessageCard.swift`). Now also exposes KG claims/entities the UI previously hid.
- Additive/reversible: optional field, defaulted backend values, renders only when a search occurred. NO backend/schema change. NOT gated on #104.
- New test: `fichero-tests/RetrievalInfoTests.swift` (pluralization, didSearch gating, Codable round-trip). Test-target = synced group, no pbxproj edit.
- No new main-target .swift files (only edits) → no add-swift-file.rb / pbxproj change.
- swiftlint: clean on changed lines (3 pre-existing warnings in ChatServiceGenerated unrelated to edit).
- Build gate (isolated DD, CODE_SIGNING_ALLOWED=NO): all Swift sources COMPILED + LINKED (22 Ld steps, 0 swiftc errors). Build's only failure = "Embed Fichero Engine" run-script phase (needs pre-built engine app absent in this worktree) — environmental, not a code defect.
- NOT pushed.

## #2571 — Stage 2 parity: card + map views (additive)
Done by f_fichero_claude_swiftui (2026-06-28). Commit 9360ed41, authored Claude.

- Added the retrieval line to `MessageCard` (icon/grid: full "Searched library · N documents · M claims") and `MessageMapCard` (space-tight map: compact magnifyingglass indicator beside the existing source-count badge). Now all three chat displays (bubble/card/map) show the search-as-a-tool step.
- View-only, reuses already-tested `RetrievalInfo` — no new test needed.
- swiftlint clean. Isolated build (DD cached): 0 swiftc errors, MessageCard recompiled + relinked; only failure = "Embed Fichero Engine" script phase (engine app absent in worktree) — environmental, not a code defect.
- NOT pushed.
