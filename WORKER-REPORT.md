## #2801/#2811/#2813 compact-layout unit tests — VERIFY + STOP — 2026-07-03, f_fichero_claude_swiftui

Task: add fichero-tests/ unit tests locking the pure layout-decision logic the compact fixes touched. On inspection the pure logic is ALREADY comprehensively covered, so no net-new tests were written (per the "if not cleanly unit-testable, do not force it — report and STOP" instruction; here it's the stronger "already locked in" case). No production code changed.

### Named helpers — already tested (all pure `static`, macOS-target-testable)
- `shellWindowMinWidth` returns 0 (not 520) when horizontalSizeClass == .compact (#2801) → `AdaptiveShellPolicyTests.testCompactShellMinWidthIsZeroSoContentFitsPhoneWidth` (+ `testRegularShellMinWidthUnchangedByTheCompactGuard`).
- `shouldUseCompactNavigationFlow(horizontalSizeClass:)` → `AdaptiveShellPolicyTests.testCompactNavigationFlowIsCompactOnly`.
- `defaultPreferredCompactColumn` (.detail) → `testCompactSplitViewRootsAtDetailColumn` + `LayoutModeTests.testCompactShellRootsAtDetailAndHidesSidebarColumn`.
- `shouldRenderSidebarColumn(...)` compact→false → `testSidebarRenderedPredicateMatchesActualSidebarColumnGate`.
- `shouldUseSplittablePane(...)` compact→false → `SplittablePanePolicyTests` (2) + `testSplittablePanesCollapseWhenWindowIsTooNarrow`.
- `windowMinWidth`, `shellCollapsePolicy` (narrow/inspector-band/roomy), `adaptiveWidescreenAvailableWidth`, `WidescreenPanePlan.make`, `AdaptiveAppleShellRoute.resolve` → all covered in `AdaptiveShellPolicyTests`/`LayoutModeTests`.
- `InspectorPlacement.adaptiveDefault`/`adaptivePresentation` (chrome-visibility on size class) → `InspectorPresenterTests` + `LayoutModeTests.testInspectorPlacementAdaptsToCompactWidth`.

### #2811 / #2813 — NOT cleanly unit-testable (reported, not forced)
Both are INLINE view-body guards, not extracted helpers:
- #2811 (hide Mac detail chrome at compact): `if horizontalSizeClass != .compact` around the tab strip / location + status path bars in `detailShellColumn` (a `some View`).
- #2813 (hide pane-toggle buttons in compact reader flow): `&& !Self.shouldUseCompactNavigationFlow(horizontalSizeClass:)` on the pane-toggle group in `contentPaneToolbarContent` (a `ToolbarContent`).
Their underlying predicate (`shouldUseCompactNavigationFlow`, and on macOS the equivalent `!= .compact`) is already tested; only the SwiftUI wiring is unverified, and asserting that needs view rendering — the entangled case the instruction says to skip. Optional future lock: extract the #2811 inline predicate into a named `static` helper (mirroring `shouldRenderSidebarColumn`) and reuse #2813's, then unit-test — a small production refactor, held for Daniel rather than done unilaterally.

### Gate
`xcodebuild build-for-testing` (isolated, scratch DerivedData, CODE_SIGNING_ALLOWED=NO, macOS) → `** TEST BUILD SUCCEEDED **` (exit 0). Confirms the existing layout test suite compiles cleanly on HEAD. NOT pushed.

The non-design-gated Fable backlog remains DONE. EPIC #2810 architecture items (single NavigationStack / iPad slide-overs / swipe paging) are needs-design — NOT started, awaiting Daniel.
