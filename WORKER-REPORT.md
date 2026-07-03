
## UI Reform — Representations (#93), net-new UX-review fixes — 2026-06-28, f_fichero_claude_swiftui

### #2801 — iPhone shell min-width clamps content off-screen — DONE
Commit bf65e42a, authored Claude.
- Root: ContentView .frame(minWidth: shellWindowMinWidth) unconditional; on iOS paneAwareDetailMinWidth returns contentMinWidth (520) when supportsReadingWorkspace is false → 520 clamps content off-screen on a 390–430pt iPhone.
- Fix: static shellWindowMinWidth returns 0 when horizontalSizeClass == .compact. RUNTIME check (not #if os(iOS)) — macOS never reports compact, so Mac unchanged, and the branch is unit-testable on the macOS test target.
- Test: AdaptiveShellPolicyTests +2 (compact+520 detail → 0; regular path stays non-zero). App build green (isolated xcodebuild, no signing).

### #2803 — dark-mode invisible text (hardcoded near-white paper bg) — DONE
Commit 3317225e, authored Claude.
- EditorView.textPreview/genericPreview (unreferenced but fixed for correctness) + ImageEditorView (live compare/editor pane) used Color(red:253/255,…) under default-label Text → white-on-white in dark mode.
- Fix: Color(platformColor: .textBackgroundColor) — adaptive (macOS textBackgroundColor / iOS systemBackground), darkens in dark mode. Swept: PDFPageView's PDFKit paper bg is intentional, left as-is. App build green.

### #2805 — openWindow detach actions are silent no-ops on iPhone — DONE
Commit 1faf1bd2, authored Claude.
- 5 sites called openWindow(id:) unguarded; FicheroApp_iOS has one WindowGroup → dead buttons on iPhone. Mirrored ArtifactsInspectorPane's @Environment(\.supportsMultipleWindows) gate:
  - Notes/Annotations/CitationsInspectorPane: guard supportsMultipleWindows in openDetailWindow().
  - ActivityViewHelpers: hide the pop-to-window button when unsupported.
  - WorkflowEditor+Actions: skip only the monitor pop (workflow still runs).
- App build green (isolated xcodebuild, no signing).

All 3 iOS-affecting; macOS builds green here — manager to run the iOS-target build to exercise #if os(iOS) paths. NOT pushed.
