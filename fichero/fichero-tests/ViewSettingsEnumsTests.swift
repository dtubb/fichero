@testable import Fichero
import Foundation
import XCTest

/// Tests for the ViewSettings view-mode enums (#1989 App coverage).
/// The high-value lock is the PreviewMode ⇆ PreviewLayout facade (#2032): a
/// wrong mapping silently puts the document preview in the wrong place. Also
/// locks LibraryLayout raw values / icons / Codability.
final class ViewSettingsEnumsTests: XCTestCase {

    // MARK: - LibraryLayout

    func testLibraryLayoutCasesRawValuesAndIcons() {
        XCTAssertEqual(LibraryLayout.allCases.count, 4)
        XCTAssertEqual(LibraryLayout.icons.rawValue, "Icons")
        XCTAssertEqual(LibraryLayout.list.rawValue, "List")
        XCTAssertEqual(LibraryLayout.table.rawValue, "Table")
        XCTAssertEqual(LibraryLayout.map.rawValue, "Map")
        for layout in LibraryLayout.allCases {
            XCTAssertFalse(layout.icon.isEmpty, "\(layout) icon")
        }
    }

    func testLibraryLayoutCodableRoundTrip() throws {
        for layout in LibraryLayout.allCases {
            let restored = try JSONDecoder().decode(
                LibraryLayout.self,
                from: JSONEncoder().encode(layout)
            )
            XCTAssertEqual(layout, restored)
        }
    }

    // MARK: - PreviewMode <-> PreviewLayout bridge

    func testPreviewModeMapsToExpectedLayout() {
        XCTAssertEqual(PreviewMode.widescreen.layout, PreviewLayout.side)
        XCTAssertEqual(PreviewMode.standard.layout, PreviewLayout.bottom)
        XCTAssertEqual(PreviewMode.none.layout, PreviewLayout.hidden)
    }

    func testPreviewLayoutMapsBackToExpectedMode() {
        XCTAssertEqual(PreviewLayout.side.previewMode, PreviewMode.widescreen)
        XCTAssertEqual(PreviewLayout.bottom.previewMode, PreviewMode.standard)
        XCTAssertEqual(PreviewLayout.hidden.previewMode, PreviewMode.none)
    }

    func testPreviewBridgeRoundTripsBothDirections() {
        for mode in PreviewMode.allCases {
            XCTAssertEqual(mode.layout.previewMode, mode, "mode \(mode) lost in round-trip")
        }
        for layout in PreviewLayout.allCases {
            XCTAssertEqual(layout.previewMode.layout, layout, "layout \(layout) lost in round-trip")
        }
    }

    func testPreviewModeAndLayoutHaveSameCardinality() {
        // The facade is one-to-one; a new case on one side without the other
        // would break the bridge.
        XCTAssertEqual(PreviewMode.allCases.count, PreviewLayout.allCases.count)
    }
}
