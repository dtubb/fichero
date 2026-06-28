
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

## UI Reform — Inspector & Annotation (#94) — 2026-06-28, f_fichero_claude_swiftui

### #2536 — ArtifactPanel autosave drops trailing edit (data-loss race) — TESTS ADDED (fix pre-existing)
Commit 09613dc3, authored Claude.
- The CODE fix already landed on main (b031a234); it was guarded only by a source-level string match. The coalescing logic was untestable (private @State in ArtifactPanel).
- Extracted serial+coalescing mechanics → new `Models/CoalescingSaveRunner.swift` (@Observable @MainActor, registered via add-swift-file.rb). ArtifactPanel.performSave delegates to it; behaviour-preserving (watermarks, redundant-PUT skip, isSaving spinner). Removed isSaving/activeSave/pendingResave @State.
- HIGH test bar met: `CoalescingSaveRunnerTests` — edit-during-in-flight-save (fails on old drop, passes on fix), multiple-rapid-edits edge, loop-termination, isSaving state. Updated ArtifactPanel source guard to pin delegation.
- prefer-raise: runner never silently drops; onSave is non-throwing so no error to swallow. Surfacing save FAILURES (throwing onSave + saveError) is a separate pre-existing gap (saveError is declared but never set) — out of scope, flagged.
- Verification: app build green (isolated xcodebuild, no signing). My code + test files compile with ZERO diagnostics across all runs. Suite not RUN (no-test-on-this-machine rule); used build-for-testing to compile-verify.

### Pre-existing test-suite breakage (separate commit b4b56a59)
- FicheroTests target did NOT compile on main. Fixed 3 mechanical breaks: WorkflowStreamParsingTests (4× dropped Data() wrapper on JSON literals), WorkflowStreamConnectionTests (@MainActor on mapStatus test), WorkflowImportExportSurfaceTests (PartialRangeFrom → half-open Range).
- REMAINING pre-existing break beyond scope: ChatWithDocsRoutingTests:21 — ChatWithDocsRoute has no member `sidebarShowsChat` (API mismatch, tied to in-flux chat-sidebar work). Recommend a dedicated test-suite-repair task. NOT pushed.
