@testable import Fichero
import XCTest

final class AdaptiveShellPolicyTests: XCTestCase {
    func testAdaptiveShellDefaultsAndLegacyRestoreStayPlatformSpecific() {
        #if os(macOS)
        XCTAssertEqual(ContentView.defaultColumnVisibility, .all)
        XCTAssertEqual(ContentView.defaultColumnVisibilityRaw, 2)
        XCTAssertFalse(ContentView.shouldUseAutomaticCompactCollapse(horizontalSizeClass: nil))
        XCTAssertEqual(ContentView.preferredCompactColumn(horizontalSizeClass: nil), .detail)
        XCTAssertEqual(ContentView.restoredColumnVisibility(from: 2), .all)
        XCTAssertEqual(ContentView.persistedColumnVisibilityRaw(for: .all), 2)
        #else
        XCTAssertEqual(ContentView.defaultColumnVisibility, .detailOnly)
        XCTAssertEqual(ContentView.defaultColumnVisibilityRaw, 1)
        XCTAssertFalse(ContentView.shouldUseAutomaticCompactCollapse(horizontalSizeClass: .regular))
        XCTAssertTrue(ContentView.shouldUseAutomaticCompactCollapse(horizontalSizeClass: .compact))
        XCTAssertEqual(ContentView.preferredCompactColumn(horizontalSizeClass: .compact), .sidebar)
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

    func testCompactCollapseAlwaysUsesAutomaticVisibilityRuntimePolicy() {
        #if os(macOS)
        XCTAssertFalse(ContentView.shouldUseAutomaticCompactCollapse(horizontalSizeClass: nil))
        #else
        XCTAssertFalse(ContentView.shouldUseAutomaticCompactCollapse(horizontalSizeClass: .regular))
        XCTAssertTrue(ContentView.shouldUseAutomaticCompactCollapse(horizontalSizeClass: .compact))
        #endif
    }
}
