@testable import Fichero
import XCTest

/// The library's tier selector (2026-08-22).
///
/// These pin the two decisions that are easy to get wrong later: what the grid
/// opens on, and that the wire contract cannot drift when a UI label changes.
final class LibraryLevelTests: XCTestCase {

    // MARK: - The default

    /// A 1926 diary folder holds 75 openings. At `stored` the reader sees 75
    /// spreads and cannot reach an individual page without drilling into each
    /// one — which is what was reported broken. Wrong-but-one-click-away beats
    /// right-but-unreachable.
    func testGridOpensOnPages() {
        XCTAssertEqual(LibraryLevel.gridDefault, .content)
    }

    /// The sidebar's job is STRUCTURE. Flattening it would make the hierarchy
    /// invisible in the one surface built to show it — you could never
    /// navigate to a spread, only to its pages.
    func testSidebarAlwaysShowsTheTreeAsHeld() {
        XCTAssertEqual(LibraryLevel.sidebar, .stored)
    }

    func testTheTwoSurfacesDisagreeOnPurpose() {
        XCTAssertNotEqual(LibraryLevel.gridDefault, LibraryLevel.sidebar)
    }

    // MARK: - Wire contract

    /// `wireValue` is deliberately not `rawValue`: renaming a case for the UI
    /// must not silently change what the engine is asked for.
    func testWireValuesMatchTheEngineVocabulary() {
        XCTAssertEqual(LibraryLevel.stored.wireValue, "stored")
        XCTAssertEqual(LibraryLevel.content.wireValue, "content")
    }

    func testEveryCaseHasAWireValue() {
        for level in LibraryLevel.allCases {
            XCTAssertFalse(level.wireValue.isEmpty, "\(level) has no wire value")
        }
    }

    // MARK: - Persistence round trip

    func testRoundTripsThroughItsRawValue() {
        for level in LibraryLevel.allCases {
            XCTAssertEqual(LibraryLevel(rawValue: level.rawValue), level)
        }
    }

    /// A stored preference from a future or corrupted build must not crash the
    /// grid — the caller falls back to the default.
    func testAnUnknownStoredValueIsNil() {
        XCTAssertNil(LibraryLevel(rawValue: "gatefolds"))
    }

    // MARK: - Presentation

    /// The reader thinks in spreads and pages, not container nodes.
    func testTitlesAreTheReadersWords() {
        XCTAssertEqual(LibraryLevel.stored.title, "Spreads")
        XCTAssertEqual(LibraryLevel.content.title, "Pages")
    }

    func testEveryCaseIsPresentable() {
        for level in LibraryLevel.allCases {
            XCTAssertFalse(level.title.isEmpty)
            XCTAssertFalse(level.systemImage.isEmpty)
            XCTAssertFalse(level.help.isEmpty)
        }
    }
}
