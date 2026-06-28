
## Chat & Agent milestone (#102) — 2026-06-28, f_fichero_claude_swiftui

### #2639 — render markdown + Xcode-style bubbles in sidebar chat — DONE
Commit c04b58f2, authored Claude.
- New native, dependency-free `Views/Components/MarkdownText.swift` (headings, lists, blockquotes, fenced code blocks, inline bold/italic/code/links via AttributedString). Registered via add-swift-file.rb.
- Wired into `MessageBubble` (the sidebar `.list` view = the bug's site); MessageBubble already had the Xcode-style role-coloured bubble layout, only the content Text was swapped. MessageCard preview Text left as-is (clamped preview).
- Reusable in Components/ so MarkdownCanvas (#2264) can adopt later — reuse, not a parallel chat component.
- Test: `fichero-tests/MarkdownBlockTests.swift` (heading levels, hash-without-space, ordered/unordered lists, fenced code doesn't parse inside, blockquote, paragraph join, mixed-doc order).
- swiftlint clean (refactored parser into helpers for complexity/length; renamed short vars). Isolated build: 0 swiftc errors, both files compiled + linked; only failure = environmental engine-embed phase. NOT pushed.

### #2034 — left toolbar one sidebar + one chat toggle — HELD (design)
- Audit: NO duplicate sidebar toggle in the rendered toolbar. Live left zone = back/forward; sidebar toggle = NavigationSplitView system; inspector toggle = right. Only second `sidebar.left` is in `MainToolbar.swift` = DEAD CODE (only its own #Preview).
- No chat toggle/rail exists. Chat toggle target = Xcode-style chat that REPLACES the left sidebar (per Daniel 2026-06-16), still converging in master-plan §7.10. Parent EPIC #2030 = needs-design; needs running-app visual verification (unavailable in this worktree).
- Held per Daniel's call. Findings posted to issue #2034.

### #1846 — chat first-party right-rail — HELD (shelved by owner)
- #1846's own latest comment (Daniel) SHELVES the right-of-inspector placement: "Superseded by EPIC #2253; master plan §6d/§7.10 resolves chat placement to the left/top … this right-rail placement is shelved." Building it would contradict documented direction.
- No code written. Held per Daniel's call. Findings posted to issue #1846.

Net: 1 of 3 shipped (#2639); #2034 + #1846 held on the unresolved §7.10 chat-placement decision. Awaiting Daniel.

### #1891 — ComparisonDetailView URLSession + custom transcript modes — DONE
Commit ea330da2, authored Claude.
- URLSession: ALREADY migrated. ComparisonDetailView+Actions.loadComparison() uses the generated client (client.api.getComparison…). Swept chat + ModelComparison dirs: NO raw URLSession/URLRequest/dataTask. Mandate met.
- Transcript modes: the icon/table/map oddity was in ChatMessagesList (NOT ComparisonDetailView, which has no view-mode switch). ChatMessagesList now always renders native bubbles. Removed unused MessageCard + MessageMapCard structs + the dead displayMode param through ChatView → ChatMessagesList + 3 call sites (preview, ResearchChatPane, ContentView+Navigation).
- ChatMapGrid.swift now unreferenced (map mode only) — left in place (no safe pbxproj remove tool; never hand-edit pbxproj); flagged for a follow-up file-removal sweep on issue #1891.
- swiftlint clean. Isolated build: 0 swiftc errors, all changed files compiled + linked; only failure = environmental engine-embed phase. NOT pushed.
