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
        XCTAssertEqual(LibraryLayout.allCases.count, 6)
        XCTAssertEqual(LibraryLayout.icons.rawValue, "Icons")
        XCTAssertEqual(LibraryLayout.list.rawValue, "List")
        XCTAssertEqual(LibraryLayout.table.rawValue, "Table")
        // Miller columns (#4160 step 4). Raw value is "MillerColumns", NOT
        // "Columns" — the table's user-facing label was "Columns" until now,
        // and a raw value that collides with an old LABEL invites confusion
        // in persisted-state archaeology even though labels never persist.
        XCTAssertEqual(LibraryLayout.columns.rawValue, "MillerColumns")
        XCTAssertEqual(LibraryLayout.canvas.rawValue, "Canvas")
        XCTAssertEqual(LibraryLayout.space.rawValue, "Space")
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

    // MARK: - TranscriptLayout (#3805)

    /// Diplomatic must be the default: the manuscript's line structure is real data
    /// and must never be lost silently (Daniel). Reading reflow is opt-in.
    func testTranscriptLayoutDefaultsToDiplomatic() {
        XCTAssertEqual(TranscriptLayout.defaultValue, .diplomatic)
    }

    /// Raw values are the persisted @AppStorage identity — a rename would silently
    /// reset every user's choice, so pin them along with the stable storage key.
    func testTranscriptLayoutRawValuesAndStorageKeyAreStable() {
        XCTAssertEqual(TranscriptLayout.diplomatic.rawValue, "diplomatic")
        XCTAssertEqual(TranscriptLayout.reading.rawValue, "reading")
        XCTAssertEqual(TranscriptLayout.storageKey, "fichero.reader.transcriptLayout")
        XCTAssertEqual(TranscriptLayout.allCases.count, 2)
        for layout in TranscriptLayout.allCases {
            XCTAssertFalse(layout.label.isEmpty, "\(layout) label")
            XCTAssertEqual(layout.id, layout.rawValue)
        }
    }
}
