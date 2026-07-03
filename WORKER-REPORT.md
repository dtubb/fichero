
## #2806 — compact/touch polish sweep — 2026-07-03, f_fichero_claude_swiftui
Six separate commits, each macOS build-gated (isolated xcodebuild, scratch DD, CODE_SIGNING_ALLOWED=NO). Dynamic Type item SKIPPED per instruction (needs judgement; leave intentional scaled/display fonts for a separate pass).

- (1) 705a417f — ChainListContent: replaced the row .onTapGesture(count:2) on List(selection:) with native .contextMenu(forSelectionType:menu:primaryAction:) — no custom gesture fighting selection; primaryAction opens (double-click Mac / tap-to-open touch).
- (2) 3eb7814e — canvas grab handles: WorkflowPortView (12pt port) + Spatial2DCanvasGestures resize handle (12pt) keep the visual but expand the hit frame + contentShape to 44pt on touch (#if !os(macOS)); Mac keeps precise 12pt.
- (3) 0e62737c — hardcoded .blue → Color.accentColor at the ACCENT-TINT sites only (TriggerDetailView+Configuration, ScheduleDetailView, ActionPickerView×2, WorkflowPreviewSheet×2). LEFT status colors (case "running" → .blue) and builtin/custom blue-vs-orange pairs — those are deliberate palettes, not the app tint.
- (4) 803e5a6c — PickerMiniToolbar: .pickerStyle(.menu) at compact instead of the overflowing capped segmented control; Mac/iPad-regular keep segmented. Picker factored into a shared helper.
- (5) d0950866 — SearchResultsDisplay.tableView falls back to the pane's existing listView at compact (mirrors LibraryView table); columns kept on Mac/iPad-regular.
- (6) 898c7b16 — sheet footers → native toolbar: EntitySplitSheet / AIProviderAddModelsSheet / MCPServersSheet wrapped in NavigationStack with .toolbar ToolbarItem(.cancellationAction/.confirmationAction) + navigationTitle, replacing hand-rolled HStack footers (wrong placement on iOS). macOS keeps its fixed frame.

All macOS build green. (2)/(4)/(5)/(6) are compact/iOS-affecting — manager iOS-target build to exercise. NOT pushed.

NOTE: EPIC #2810 net-new architecture items (single compact NavigationStack, iPad slide-overs, swipe paging) are needs-design — NOT started; Daniel to sequence.
