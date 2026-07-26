@testable import Fichero
import XCTest
// swiftlint:disable type_body_length file_length

final class AdaptiveShellPolicyTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testAdaptiveShellDefaultsAndLegacyRestoreStayPlatformSpecific() {
        #if os(macOS)
        XCTAssertEqual(ContentView.defaultColumnVisibility, .all)
        XCTAssertEqual(ContentView.defaultColumnVisibilityRaw, 2)
        XCTAssertEqual(ContentView.restoredColumnVisibility(from: 2), .all)
        XCTAssertEqual(ContentView.persistedColumnVisibilityRaw(for: .all), 2)
        #else
        XCTAssertEqual(ContentView.defaultColumnVisibility, .detailOnly)
        XCTAssertEqual(ContentView.defaultColumnVisibilityRaw, 1)
        XCTAssertEqual(ContentView.restoredColumnVisibility(from: 2), .detailOnly)
        XCTAssertEqual(ContentView.persistedColumnVisibilityRaw(for: .all), 3)
        XCTAssertEqual(ContentView.restoredColumnVisibility(from: 3), .doubleColumn)
        #endif
    }

    func testCompactSplitViewRootsAtDetailColumn() {
        // On a phone the collapsed stack should land on the content/reader
        // (document list), with the sidebar one swipe-back away (#2329/#2334).
        XCTAssertEqual(ContentView.defaultPreferredCompactColumn, .detail)
    }

    func testAdaptiveShellPersistenceKeepsCollapsedAndExplicitWideStatesDistinct() {
        XCTAssertEqual(ContentView.restoredColumnVisibility(from: 0), .automatic)
        XCTAssertEqual(ContentView.restoredColumnVisibility(from: 1), .detailOnly)
        XCTAssertEqual(ContentView.persistedColumnVisibilityRaw(for: .detailOnly), 1)
        XCTAssertEqual(ContentView.persistedColumnVisibilityRaw(for: .automatic), 0)
    }

    func testWindowMinimumSeparatesMacShellChromeFromCompactDetailLayout() {
        let detailWidth = 600.0

        #if os(macOS)
        let expected = ContentView.sidebarMinWidth + detailWidth + ContentView.inspectorMinWidth
        XCTAssertEqual(
            ContentView.windowMinWidth(
                sidebarVisible: true,
                inspectorVisible: true,
                detailMinWidth: detailWidth
            ),
            expected
        )
        #else
        XCTAssertEqual(
            ContentView.windowMinWidth(
                sidebarVisible: true,
                inspectorVisible: true,
            detailMinWidth: detailWidth
        ),
            detailWidth
        )
        #endif
    }

    func testNarrowWindowCollapsesSecondaryPanesBeforePersisting() {
        let detailWidth = 600.0
        let narrowWidth = ContentView.sidebarMinWidth + detailWidth - 1

        let policy = ContentView.shellCollapsePolicy(
            windowWidth: narrowWidth,
            horizontalSizeClass: .regular,
            sidebarVisible: true,
            inspectorVisible: true,
            detailMinWidth: detailWidth
        )

        XCTAssertTrue(policy.collapseSidebar)
        XCTAssertTrue(policy.collapseInspector)
    }

    func testWiderWindowKeepsPreferredMacOrIPadSidebarState() {
        let detailWidth = 600.0
        let roomyWidth =
            ContentView.sidebarMinWidth + detailWidth + ContentView.inspectorMinWidth + 40

        let policy = ContentView.shellCollapsePolicy(
            windowWidth: roomyWidth,
            horizontalSizeClass: .regular,
            sidebarVisible: true,
            inspectorVisible: true,
            detailMinWidth: detailWidth
        )

        XCTAssertFalse(policy.collapseSidebar)
        XCTAssertFalse(policy.collapseInspector)
    }

    func testNarrowWindowDropsShellMinWidthToDetailWidth() {
        let detailWidth = 600.0
        let narrowWidth = ContentView.sidebarMinWidth + detailWidth - 1

        XCTAssertEqual(
            ContentView.shellWindowMinWidth(
                windowWidth: narrowWidth,
                horizontalSizeClass: .regular,
                sidebarVisible: true,
                inspectorVisible: true,
                detailMinWidth: detailWidth
            ),
            detailWidth
        )
    }

    func testCompactShellMinWidthIsZeroSoContentFitsPhoneWidth() {
        // #2801: on a compact (iPhone) layout the content column must be free to
        // shrink; a 520pt content minimum would clamp it off-screen on a
        // 390–430pt phone. The shell minimum drops to 0 regardless of the
        // detail minimum, and independent of window width.
        XCTAssertEqual(
            ContentView.shellWindowMinWidth(
                windowWidth: 400,
                horizontalSizeClass: .compact,
                sidebarVisible: true,
                inspectorVisible: true,
                detailMinWidth: ContentView.contentMinWidth
            ),
            0
        )
    }

    func testRegularShellMinWidthUnchangedByTheCompactGuard() {
        // The compact guard must not touch the regular (Mac / iPad) path.
        let detailWidth = 600.0
        let roomyWidth =
            ContentView.sidebarMinWidth + detailWidth + ContentView.inspectorMinWidth + 40
        XCTAssertNotEqual(
            ContentView.shellWindowMinWidth(
                windowWidth: roomyWidth,
                horizontalSizeClass: .regular,
                sidebarVisible: true,
                inspectorVisible: true,
                detailMinWidth: detailWidth
            ),
            0
        )
    }

    func testRoomyWindowKeepsFullShellMinWidthForMacAndiPadLayouts() {
        let detailWidth = 600.0
        let roomyWidth =
            ContentView.sidebarMinWidth + detailWidth + ContentView.inspectorMinWidth + 40

        XCTAssertEqual(
            ContentView.shellWindowMinWidth(
                windowWidth: roomyWidth,
                horizontalSizeClass: .regular,
                sidebarVisible: true,
                inspectorVisible: true,
                detailMinWidth: detailWidth
            ),
            ContentView.windowMinWidth(
                sidebarVisible: true,
                inspectorVisible: true,
                detailMinWidth: detailWidth
            )
        )
    }

    func testInspectorCollapseBandRelaxesShellMinWidthToSidebarAndDetail() {
        let detailWidth = 600.0
        let inspectorBandWidth =
            ContentView.sidebarMinWidth + detailWidth + ContentView.inspectorMinWidth - 1

        let policy = ContentView.shellCollapsePolicy(
            windowWidth: inspectorBandWidth,
            horizontalSizeClass: .regular,
            sidebarVisible: true,
            inspectorVisible: true,
            detailMinWidth: detailWidth
        )

        XCTAssertFalse(policy.collapseSidebar)
        XCTAssertTrue(policy.collapseInspector)
        XCTAssertEqual(
            ContentView.shellWindowMinWidth(
                windowWidth: inspectorBandWidth,
                horizontalSizeClass: .regular,
                sidebarVisible: true,
                inspectorVisible: true,
                detailMinWidth: detailWidth
            ),
            ContentView.sidebarMinWidth + detailWidth
        )
    }

    func testCompactNavigationFlowIsCompactOnly() {
        #if os(macOS)
        XCTAssertFalse(ContentView.shouldUseCompactNavigationFlow(horizontalSizeClass: nil))
        XCTAssertFalse(ContentView.shouldUseCompactNavigationFlow(horizontalSizeClass: .compact))
        #else
        XCTAssertFalse(ContentView.shouldUseCompactNavigationFlow(horizontalSizeClass: nil))
        XCTAssertFalse(ContentView.shouldUseCompactNavigationFlow(horizontalSizeClass: .regular))
        XCTAssertTrue(ContentView.shouldUseCompactNavigationFlow(horizontalSizeClass: .compact))
        #endif
    }

    func testAdaptiveAppleShellRouteUsesStackOnlyForCompactWidth() {
        #if os(macOS)
        XCTAssertEqual(AdaptiveAppleShellRoute.resolve(horizontalSizeClass: nil), .split)
        XCTAssertEqual(AdaptiveAppleShellRoute.resolve(horizontalSizeClass: .compact), .split)
        #else
        XCTAssertEqual(AdaptiveAppleShellRoute.resolve(horizontalSizeClass: nil), .split)
        XCTAssertEqual(AdaptiveAppleShellRoute.resolve(horizontalSizeClass: .regular), .split)
        XCTAssertEqual(AdaptiveAppleShellRoute.resolve(horizontalSizeClass: .compact), .stack)
        #endif
    }

    func testSplittablePanesCollapseWhenWindowIsTooNarrow() {
        XCTAssertFalse(
            ContentView.shouldUseSplittablePane(
                horizontalSizeClass: .compact,
                windowWidth: 1200,
                minimumWidth: 800
            )
        )
        XCTAssertFalse(
            ContentView.shouldUseSplittablePane(
                horizontalSizeClass: .regular,
                windowWidth: 799,
                minimumWidth: 800
            )
        )
        XCTAssertTrue(
            ContentView.shouldUseSplittablePane(
                horizontalSizeClass: .regular,
                windowWidth: 801,
                minimumWidth: 800
            )
        )
    }

    func testSidebarRenderedPredicateMatchesActualSidebarColumnGate() {
        XCTAssertFalse(
            ContentView.shouldRenderSidebarColumn(
                horizontalSizeClass: .compact,
                showSidebar: true,
                columnVisibility: .all
            )
        )
        XCTAssertFalse(
            ContentView.shouldRenderSidebarColumn(
                horizontalSizeClass: .regular,
                showSidebar: true,
                columnVisibility: .detailOnly
            )
        )
        XCTAssertFalse(
            ContentView.shouldRenderSidebarColumn(
                horizontalSizeClass: .regular,
                showSidebar: false,
                columnVisibility: .all
            )
        )
        XCTAssertTrue(
            ContentView.shouldRenderSidebarColumn(
                horizontalSizeClass: .regular,
                showSidebar: true,
                columnVisibility: .all
            )
        )
    }

    func testAdaptiveWidescreenAvailableWidthOnlySubtractsInspector() {
        XCTAssertNil(
            ContentView.adaptiveWidescreenAvailableWidth(
                windowWidth: nil,
                inspectorVisible: true
            )
        )
        XCTAssertEqual(
            ContentView.adaptiveWidescreenAvailableWidth(
                windowWidth: 200,
                inspectorVisible: false
            ),
            200
        )
        XCTAssertEqual(
            ContentView.adaptiveWidescreenAvailableWidth(
                windowWidth: ContentView.inspectorMinWidth,
                inspectorVisible: true
            ),
            0
        )
    }

    func testWidescreenPanePlanStillCollapsesAtZeroAvailableWidth() {
        let plan = WidescreenPanePlan.make(
            showDocumentGrid: true,
            showDocumentCanvas: true,
            showReadingPane: true,
            availableWidth: 0
        )

        XCTAssertTrue(plan.showsLibraryPane)
        XCTAssertFalse(plan.showsCanvasPane)
        XCTAssertFalse(plan.showsReadingPane)
        XCTAssertEqual(plan.minimumWidth, ContentView.contentListMinWidth)
    }

    func testPersistentShellChromeStaysInSplitColumns() throws {
        let contentSource = try Self.appSource("Views/Shell/ContentView/ContentView.swift")
        let buildersSource = try ([
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+InspectorContainer.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+DetailLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+CompactReader.swift"),
        ].joined(separator: "\n"))
        let workspaceRootSource = try Self.appSource("Views/Library/Workspace/LibraryWorkspaceRoot.swift")

        // The split view and its columns live in Layout/ContentView+RootLayout
        // since 408e4ae81; ContentView.swift keeps only `body`.
        XCTAssertTrue(buildersSource.contains("NavigationSplitView("))
        XCTAssertTrue(buildersSource.contains("detailShellColumn"))
        XCTAssertTrue(contentSource.contains("var body: some View"))
        XCTAssertTrue(buildersSource.contains("var detailShellColumn: some View"))
        XCTAssertTrue(buildersSource.contains("detailTabStrip"))
        // The location path bar + pane breadcrumb strip are RETIRED (#4102
        // dedupe): the path renders only in the toolbar's principal
        // breadcrumb; the bottom bar is Finder-style selection status.
        XCTAssertFalse(buildersSource.contains("detailLocationPathBar"))
        XCTAssertFalse(buildersSource.contains("breadcrumbBar"))
        XCTAssertTrue(buildersSource.contains("detailStatusPathBar"))
        XCTAssertTrue(buildersSource.contains("WindowOpener.open(libraryId: windowState.libraryId, asTab: true"))
        XCTAssertTrue(workspaceRootSource.contains("AdaptiveAppleShellHost"))
    }

    func testSelectionStatusTextIsFinderStyleWithoutPath() throws {
        // file_length: ContentView+State split into ContentView+State*; read them all concatenated.
        let stateSource = try [
            Self.appSource("Views/Shell/ContentView/ContentView+StateDisplay.swift"),
            Self.appSource("Views/Shell/ContentView/ContentView+StateSelection.swift"),
            Self.appSource("Views/Shell/ContentView/ContentView+StateLayout.swift"),
            Self.appSource("Views/Shell/ContentView/ContentView+StatePreview.swift"),
            Self.appSource("Views/Shell/ContentView/ContentView+StateEvents.swift"),
        ].joined(separator: "\n")

        XCTAssertTrue(stateSource.contains("var selectionStatusText: String"))
        XCTAssertTrue(stateSource.contains("\"\\(browserSelection.count) items selected\""))
        // selectionPathText is RETIRED (#4102 dedupe): the status bar shows
        // WHAT is selected, never the path — the path lives only in the
        // toolbar's principal breadcrumb.
        XCTAssertFalse(stateSource.contains("var selectionPathText: String"))
    }

    func testToolbarSearchStaysBesideContentTitle() throws {
        let toolbarSource = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")
        guard let principalRange = toolbarSource.range(of: "var principalToolbarContent: some ToolbarContent") else {
            XCTFail("principal toolbar content missing")
            return
        }
        let principalSource = toolbarSource[principalRange.lowerBound...]

        XCTAssertTrue(principalSource.contains("Text(toolbarTitle)"))
        // ToolbarSearchableModifier moved out of ContentView.swift with
        // 408e4ae81's view-builder split; it is declared in the toolbar file
        // and applied by the root layout.
        XCTAssertTrue(toolbarSource.contains("ToolbarSearchableModifier"))
    }

    func testBottomEdgeFiltersStayPaneScoped() throws {
        // #4061: the sidebar filter moved out of a standalone `sidebarFilterBar`
        // in `SidebarView+ViewComponents` and into the shared bottom
        // `SidebarBottomToolbar`. The filter is still pane-scoped (it still
        // drives `filteredLibraryHeaders`); it just lives in the unified
        // bottom toolbar chrome now.
        let sidebarComponentsSource = try Self.appSource(
            "Views/Sidebar/Sections/SidebarView+ViewComponents.swift"
        )
        let sidebarBottomToolbarSource = try Self.appSource(
            "Views/Sidebar/Sections/SidebarBottomToolbar.swift"
        )
        let sidebarHelpersSource = try Self.appSource("Views/Sidebar/Sections/SidebarView+Helpers.swift")
        let annotationsSource = try Self.appSource(
            "Views/Inspector/Notes/DocumentInspectorAnnotationsTab.swift"
        )

        XCTAssertFalse(sidebarComponentsSource.contains("sidebarFilterBar"),
                       "standalone sidebarFilterBar is gone — filter lives in the bottom toolbar (#4061)")
        XCTAssertTrue(sidebarBottomToolbarSource.contains("TextField(\"Filter\", text: sidebarFilterText)"),
                      "sidebar filter TextField lives in the shared bottom toolbar (#4061)")
        XCTAssertTrue(sidebarHelpersSource.contains("var filteredLibraryHeaders: [SidebarItem]"))
        XCTAssertTrue(annotationsSource.contains("annotationFilterBar"))
        XCTAssertTrue(annotationsSource.contains("TextField(\"Search notes, tags, claim id…\", text: $searchText)"))
    }

    func testContentPaneControlsLiveInTopToolbar() throws {
        let contentSource = try Self.appSource("Views/Shell/ContentView/ContentView.swift")
        let toolbarSource = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")
        let buildersSource = try ([
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+InspectorContainer.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+DetailLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+CompactReader.swift"),
        ].joined(separator: "\n"))

        // `contentPaneToolbarContent` is declared in the toolbar file and
        // consumed by the Layout/ builders — it left ContentView.swift with
        // 408e4ae81's view-builder split, so assert on its real homes.
        XCTAssertFalse(contentSource.contains("contentPaneToolbarContent"))
        XCTAssertTrue(toolbarSource.contains("contentPaneToolbarContent"))
        XCTAssertTrue(buildersSource.contains("contentPaneToolbarContent"))
        XCTAssertTrue(toolbarSource.contains("viewDisplayModeMenu"))
        XCTAssertTrue(toolbarSource.contains("setCanvasPaneVisible(!showDocumentCanvas)"))
        XCTAssertTrue(toolbarSource.contains("setReadingPaneVisible(!showReadingPane)"))
        XCTAssertFalse(buildersSource.contains("viewSettings.previewMode = .none"))
    }

    func testPdfReaderUsesTheExistingReadingLayout() throws {
        let buildersSource = try ([
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+InspectorContainer.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+DetailLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+CompactReader.swift"),
        ].joined(separator: "\n"))

        XCTAssertTrue(buildersSource.contains("PDFReadingView("))
        XCTAssertTrue(buildersSource.contains("contentWidth: $pageContentPaneWidth"))
        XCTAssertTrue(buildersSource.contains("SwipeSiblingNavigator("))
    }

    func testWidescreenLibraryPaneIsClippedToItsSplitColumn() throws {
        let buildersSource = try ([
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+InspectorContainer.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+DetailLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+CompactReader.swift"),
        ].joined(separator: "\n"))

        XCTAssertTrue(buildersSource.contains("adaptiveSplittablePane(storageKey: \"library\")"))
        XCTAssertTrue(buildersSource.contains(".clipped()"))
        XCTAssertTrue(buildersSource.contains("must never paint past its own split"))
    }

    func testSidebarsUseSystemGlassMaterials() throws {
        let sidebarSource = try Self.appSource("Views/Sidebar/Sections/SidebarView+ViewComponents.swift")
        let buildersSource = try ([
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+InspectorContainer.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+DetailLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+CompactReader.swift"),
        ].joined(separator: "\n"))

        XCTAssertTrue(sidebarSource.contains(".background(.bar)"))
        XCTAssertFalse(sidebarSource.contains(".background(Color(platformColor: .windowBackgroundColor))"))

        guard let detailRange = buildersSource.range(of: "var detailView: some View") else {
            XCTFail("detailView missing")
            return
        }
        let detailSource = buildersSource[detailRange.lowerBound...]
        XCTAssertTrue(detailSource.contains(".background(.bar)"))
    }

    // MARK: - Boundary hardening (#3008 verify-and-close pass)

    /// Unmeasured window (`windowWidth == nil`, e.g. a freshly opened Mac
    /// window before geometry lands) or an absent minimum must default to
    /// ALLOWING splits — a nil bound must never boot the shell collapsed.
    func testSplittablePaneNilBoundsDefaultToAllowingSplits() {
        XCTAssertTrue(
            ContentView.shouldUseSplittablePane(
                horizontalSizeClass: .regular, windowWidth: nil, minimumWidth: 800
            )
        )
        XCTAssertTrue(
            ContentView.shouldUseSplittablePane(
                horizontalSizeClass: .regular, windowWidth: 1000, minimumWidth: nil
            )
        )
        XCTAssertTrue(
            ContentView.shouldUseSplittablePane(
                horizontalSizeClass: .regular, windowWidth: nil, minimumWidth: nil
            )
        )
    }

    /// Compact width wins over nil bounds: even with no width/minimum known, a
    /// compact layout must never split (the guard is checked before the bounds).
    func testSplittablePaneCompactBeatsNilBounds() {
        XCTAssertFalse(
            ContentView.shouldUseSplittablePane(
                horizontalSizeClass: .compact, windowWidth: nil, minimumWidth: nil
            )
        )
    }

    /// The `>=` boundary: at EXACTLY the minimum width the split is allowed
    /// (the ±1 tests never probe the equality point where `>=` vs `>` bugs hide).
    func testSplittablePaneExactMinimumWidthAllowsSplit() {
        XCTAssertTrue(
            ContentView.shouldUseSplittablePane(
                horizontalSizeClass: .regular, windowWidth: 800, minimumWidth: 800
            )
        )
    }

    /// An unmeasured or non-positive window width must not force a collapse —
    /// the shell keeps its preferred (uncollapsed) state until geometry lands.
    func testShellCollapsePolicyNilOrZeroWidthDoesNotCollapse() {
        for width in [nil, 0.0, -1.0] as [Double?] {
            let policy = ContentView.shellCollapsePolicy(
                windowWidth: width,
                horizontalSizeClass: .regular,
                sidebarVisible: true,
                inspectorVisible: true,
                detailMinWidth: 600
            )
            XCTAssertFalse(policy.collapseSidebar, "width \(String(describing: width))")
            XCTAssertFalse(policy.collapseInspector, "width \(String(describing: width))")
        }
    }

    /// The sidebar-collapse threshold is strict `<`: at EXACTLY
    /// `sidebarMinWidth + detailMinWidth` the sidebar stays (only below collapses).
    func testShellCollapseSidebarThresholdIsStrictLessThan() {
        let detailWidth = 600.0
        let exactSidebarBoundary = ContentView.sidebarMinWidth + detailWidth

        let atBoundary = ContentView.shellCollapsePolicy(
            windowWidth: exactSidebarBoundary,
            horizontalSizeClass: .regular,
            sidebarVisible: true,
            inspectorVisible: false,
            detailMinWidth: detailWidth
        )
        XCTAssertFalse(atBoundary.collapseSidebar)

        let belowBoundary = ContentView.shellCollapsePolicy(
            windowWidth: exactSidebarBoundary - 1,
            horizontalSizeClass: .regular,
            sidebarVisible: true,
            inspectorVisible: false,
            detailMinWidth: detailWidth
        )
        XCTAssertTrue(belowBoundary.collapseSidebar)
    }
}
// swiftlint:enable type_body_length file_length
