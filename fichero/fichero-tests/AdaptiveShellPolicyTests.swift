@testable import Fichero
import XCTest

final class AdaptiveShellPolicyTests: XCTestCase {
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
}
