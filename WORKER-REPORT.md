
## UI Reform — Representations (#93), compact/iOS chrome batch — 2026-07-03, f_fichero_claude_swiftui

### #2802 — fixed-size sheets clip on iPhone/iPad — DONE
Commit 7ac1931d, authored Claude.
- 8 shared sheets hardcoded widths wider than an iPhone sheet → clipped content. Wrapped each fixed .frame() in #if os(macOS) so Mac keeps sized windows and iOS sheets size to the screen.
- Sites: EntityDetailView+Claims (2 sheets: 980/920), MCPServersSheet (900×600), ProvidersSettingsSheet (700×500), AddMCPServerSheet (600×550), AIProviderAddModelsSheet (600×600), EntitySplitSheet (460×440), HeuristicReviewSheet (580×480), NewEntitySheet (420×320). #if wraps a chained .frame modifier (valid Swift).
- App build green (isolated xcodebuild, no signing).

### #2811 — Mac detail chrome renders at compact width — DONE
Commit a2a4d0ad, authored Claude.
- detailShellColumn always rendered detailTabStrip + detailLocationPathBar + detailStatusPathBar, even on iPhone. Gated all three on horizontalSizeClass != .compact (Mac/iPad regular or nil → render; iPhone compact → hidden). centerContent unchanged. App build green.

### #2813 — pane-toggle buttons show in compact reader flow — DONE
Commit 68bebe00, authored Claude.
- contentPaneToolbarContent's Preview/Reading pane toggles gated on supportsReadingWorkspace only; added && !Self.shouldUseCompactNavigationFlow(horizontalSizeClass:) so they hide on iPhone (single-stack reader, toggles are no-ops). App build green.

All 3 iOS-affecting; macOS builds green here — manager to run the iOS-target build for #if os(iOS)/compact paths. NOT pushed.
