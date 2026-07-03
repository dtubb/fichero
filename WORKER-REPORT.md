
## iOS/iPad Embedding + Representations, interaction-model batch — 2026-07-03, f_fichero_claude_swiftui

### #2814 — iPhone: drop Mac window-title semantics; search → .searchable — DONE
Commit 69892185, authored Claude.
- Gated principalToolbarContent (breadcrumb lozenge + fixed 220pt search) on horizontalSizeClass != .compact; dropped the navigationSubtitle breadcrumb at compact; new CompactSearchableModifier (iOS) adds native .searchable + inline title at compact wired to runToolbarSearch. Mac/iPad-regular unchanged. macOS build green.

### #2815 — iPad multi-window: register main + document-detail scenes — DONE
Commit d5a96c64, authored Claude.
- iOS app registered a single anonymous WindowGroup → openWindow(id:"main"/"document-detail") were no-ops on iPad (where DetachInspectorButton/WindowOpener show since supportsMultipleWindows is true). Registered both scenes mirroring macOS: WindowGroup(id:"main") + WindowGroup("Document", id:"document-detail"){DocumentDetailWindow + libraryManager/claimFocusState/kgFocusState env}. Fixes WindowOpener + OpenInMenuItems "Open in New Window" (routes through id:"main"). iOS-only file (#if os(iOS) guarded) — verified vs the macOS template; macOS build green (no shared change). Manager iOS-target build to exercise.

### #2812 — compact selection armed BOTH reader push and legacy popover-inspector — DONE
Commit c83482cd, authored Claude.
- .popover(item: detailPopoverDocument) fired on compact selection (detailPopoverDocument = detailDocument when !usesDockedInspector = the compact case), doubling with the adaptive inspector's .navigationPush. Removed the popover modifier + the now-dead detailPopoverDocument binding. Compact selection now only pushes the reader; inspector is a single explicit navigation push. Mac used docked inspector (popover was nil there) → unchanged. macOS build green.

All 3 compact/iOS-affecting; macOS builds green — manager to run the iOS-target build for #if os(iOS)/compact paths. NOT pushed.
