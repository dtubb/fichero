@testable import Fichero
import SwiftUI
import XCTest

/// Tests for the keyword-cloud font-size scaling used in the search
/// empty-state pill cloud. Frequency-proportional sizing so the
/// most-used tag pops visually.
@MainActor
final class SearchResultsDisplayTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }

    // MARK: - fontSize: scaling

    func testFontSizeMinAndMaxClampToBounds() {
        let cloud: [KeywordCloudEntryDTO] = [
            KeywordCloudEntryDTO(name: "rare", count: 1),
            KeywordCloudEntryDTO(name: "common", count: 100)
        ]
        let rareSize = SearchResultsDisplay.fontSize(for: cloud[0], cloud: cloud)
        let commonSize = SearchResultsDisplay.fontSize(for: cloud[1], cloud: cloud)
        // Rare clamps to floor (11), common clamps to ceiling (17).
        XCTAssertEqual(rareSize, 11)
        XCTAssertEqual(commonSize, 17)
    }

    func testFontSizeMiddleValueInterpolates() {
        // Linear interpolation between 11 and 17 over the [lo, hi] range.
        // A doc-count exactly between min and max should produce 14.
        let cloud: [KeywordCloudEntryDTO] = [
            KeywordCloudEntryDTO(name: "lo", count: 0),
            KeywordCloudEntryDTO(name: "mid", count: 10),
            KeywordCloudEntryDTO(name: "hi", count: 20)
        ]
        let midSize = SearchResultsDisplay.fontSize(for: cloud[1], cloud: cloud)
        XCTAssertEqual(midSize, 14, accuracy: 0.1)
    }

    // MARK: - fontSize: degenerate inputs

    func testFontSizeAllSameCountFallsBackToDefault() {
        // When every entry has the same count, ratio is undefined — the
        // helper returns 12 as a sensible default.
        let cloud: [KeywordCloudEntryDTO] = [
            KeywordCloudEntryDTO(name: "a", count: 5),
            KeywordCloudEntryDTO(name: "b", count: 5),
            KeywordCloudEntryDTO(name: "c", count: 5)
        ]
        for entry in cloud {
            XCTAssertEqual(
                SearchResultsDisplay.fontSize(for: entry, cloud: cloud),
                12
            )
        }
    }

    func testFontSizeSingleEntryFallsBackToDefault() {
        let cloud: [KeywordCloudEntryDTO] = [
            KeywordCloudEntryDTO(name: "alone", count: 42)
        ]
        XCTAssertEqual(
            SearchResultsDisplay.fontSize(for: cloud[0], cloud: cloud),
            12
        )
    }

    // MARK: - KeywordCloudSizing (the hoisted, compute-once path — #3870)

    func testKeywordCloudSizingMatchesPerCallFontSize() {
        // The cloud-scanned range is computed ONCE; the result must match the old
        // per-pill `fontSize(for:cloud:)` for every entry, so hoisting changed only
        // cost, not behaviour.
        let cloud: [KeywordCloudEntryDTO] = [
            KeywordCloudEntryDTO(name: "a", count: 1),
            KeywordCloudEntryDTO(name: "b", count: 5),
            KeywordCloudEntryDTO(name: "c", count: 20)
        ]
        let sizing = KeywordCloudSizing(cloud: cloud)
        for entry in cloud {
            XCTAssertEqual(
                sizing.fontSize(for: entry),
                SearchResultsDisplay.fontSize(for: entry, cloud: cloud),
                accuracy: 0.001
            )
        }
        // And the endpoints clamp as documented.
        XCTAssertEqual(sizing.fontSize(for: cloud[0]), 11)
        XCTAssertEqual(sizing.fontSize(for: cloud[2]), 17)
    }

    func testKeywordCloudSizingDegenerateInputsFallBackTo12() {
        // No spread → default 12; empty cloud → default 12.
        let flat = [KeywordCloudEntryDTO(name: "x", count: 7), KeywordCloudEntryDTO(name: "y", count: 7)]
        XCTAssertEqual(KeywordCloudSizing(cloud: flat).fontSize(for: flat[0]), 12)
        let empty: [KeywordCloudEntryDTO] = []
        XCTAssertEqual(
            KeywordCloudSizing(cloud: empty).fontSize(for: KeywordCloudEntryDTO(name: "z", count: 1)),
            12
        )
    }

    func testSavedSearchReplayRestoresSortAndSearchType() throws {
        let viewSource = try Self.appSource("Views/Library/Search/SearchView.swift")
        let helperSource = try Self.appSource("Views/Library/Search/SearchView+Helpers.swift")

        XCTAssertTrue(viewSource.contains("searchType = search.searchType"))
        XCTAssertTrue(viewSource.contains("sortBy = search.sortBy"))
        XCTAssertTrue(viewSource.contains("sortDirection = search.sortDirection"))
        XCTAssertTrue(helperSource.contains("searchType: searchType"))
        XCTAssertTrue(helperSource.contains("sortBy: sortBy"))
        XCTAssertTrue(helperSource.contains("sortDirection: sortDirection"))
    }
}
