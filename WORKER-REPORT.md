## #2806 deferred Dynamic Type — surgical micro-font pass — 2026-07-03, f_fichero_claude_swiftui

Fable flagged fixed-pt micro-fonts as non-scaling / unreadable. SURGICAL pass on the named label-like sites only: swapped the fixed `.system(size:)` for a semantic TextStyle (`.caption2`) so they scale with Dynamic Type, while PRESERVING intentional `weight`/`design` via `Font.system(_ style:design:weight:)`. One commit, macOS build-gated (isolated xcodebuild, scratch DD, no signing) — only the environmental `Embed Fichero Engine` phase fails, zero swiftc errors.

### Converted
- WorkflowNodeView.swift `NodeProgressBadge` (335-354): count `Text` 10pt bold rounded -> `.system(.caption2, design: .rounded, weight: .bold)`; checkmark/xmark icons 10pt bold -> `.system(.caption2, weight: .bold)`; error triangle 8pt -> `.caption2`.
- SidebarView+ActivityRows.swift:195 `ActivityRunGridCell` time label 9pt -> `.caption2`.
- PDFThumbnailView.swift:69-71 `multiPageBadge` doc icon 9pt medium + page-count text 10pt semibold -> `.system(.caption2, weight: .medium/.semibold)` (kept `.monospacedDigit()`).

### SKIPPED (intentional — per blanket-font-sweep-is-wrong HARD RULE)
- LibraryViewComponents.swift:448 `TextPreviewThumbnail` 6pt mono. This is NOT a label: it renders a document's text as a miniature "shrunk page" thumbnail (#625/#2052), framed to the full thumbnail cell and clipped. It's decorative (no VoiceOver label; the row title conveys content). Converting to `.caption2` (~2x) would blow the page-preview into a few oversized clipped lines — a visual regression, and thumbnails are an image role that must stay pinned to the cell size, not scale. Left exactly as-is.

Also left alone (out of scope, intentional): the 18pt grid-cell icon, all display/weighted/proportional fonts. NOT pushed.

After this the non-design-gated Fable backlog is DONE; remaining EPIC #2810 items (compact NavigationStack, iPad slide-overs, swipe paging) are needs-design — not started.
