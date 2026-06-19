@testable import Fichero
import XCTest

final class AdaptiveShellPolicyTests: XCTestCase {
    func testAdaptiveShellDefaultsAndLegacyRestoreStayPlatformSpecific() {
        #if os(macOS)
        XCTAssertEqual(ContentView.defaultColumnVisibility, .all)
        XCTAssertEqual(ContentView.defaultColumnVisibilityRaw, 2)
        XCTAssertEqual(ContentView.preferredCompactColumn, .detail)
        XCTAssertEqual(ContentView.restoredColumnVisibility(from: 2), .all)
        XCTAssertEqual(ContentView.persistedColumnVisibilityRaw(for: .all), 2)
        #else
        XCTAssertEqual(ContentView.defaultColumnVisibility, .detailOnly)
        XCTAssertEqual(ContentView.defaultColumnVisibilityRaw, 1)
        XCTAssertEqual(ContentView.preferredCompactColumn, .detail)
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
}
