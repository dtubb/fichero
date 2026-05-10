@testable import Fichero
import XCTest

/// Tests for the recent-search history helper. The state itself lives
/// in @SceneStorage on SearchView; this exercises the pure dedup +
/// cap-at-N logic that decides what to write.
final class RecentSearchesStoreTests: XCTestCase {

    // MARK: - encode / decode round-trip

    func testEncodeDecodeRoundTrip() {
        let list = ["Asprilla", "Quibdó", "social license"]
        let encoded = RecentSearchesStore.encode(list)
        let decoded = RecentSearchesStore.decode(encoded)
        XCTAssertEqual(decoded, list)
    }

    func testDecodeEmptyJSONReturnsEmpty() {
        XCTAssertEqual(RecentSearchesStore.decode("[]"), [])
    }

    func testDecodeMalformedJSONReturnsEmpty() {
        XCTAssertEqual(RecentSearchesStore.decode("not-json"), [])
        XCTAssertEqual(RecentSearchesStore.decode(""), [])
    }

    // MARK: - recording: insertion

    func testRecordingFirstQuery() {
        let result = RecentSearchesStore.recording("Asprilla", into: [])
        XCTAssertEqual(result, ["Asprilla"])
    }

    func testRecordingPlacesNewestAtHead() {
        let prior = ["Asprilla"]
        let result = RecentSearchesStore.recording("Quibdó", into: prior)
        XCTAssertEqual(result, ["Quibdó", "Asprilla"])
    }

    // MARK: - recording: dedupe

    func testRecordingDedupsCaseInsensitively() {
        // Daniel's specific complaint: typing 'Asprilla' then 'asprilla'
        // should NOT create two entries.
        let prior = ["Asprilla"]
        let result = RecentSearchesStore.recording("asprilla", into: prior)
        XCTAssertEqual(result.count, 1)
        // The newer casing (lowercase) replaces the older.
        XCTAssertEqual(result[0], "asprilla")
    }

    func testRecordingMovesExistingEntryToHead() {
        let prior = ["Asprilla", "Quibdó", "gold"]
        let result = RecentSearchesStore.recording("Quibdó", into: prior)
        XCTAssertEqual(result, ["Quibdó", "Asprilla", "gold"])
    }

    // MARK: - recording: cap

    func testRecordingCapsAtDefault() {
        let prior = (1...10).map { "q\($0)" }
        let result = RecentSearchesStore.recording("new", into: prior)
        XCTAssertEqual(result.count, RecentSearchesStore.defaultCap)
        XCTAssertEqual(result[0], "new")
        // Oldest entry ("q10") falls off; "q1" stays.
        XCTAssertTrue(result.contains("q1"))
        XCTAssertFalse(result.contains("q10"))
    }

    func testRecordingRespectsCustomCap() {
        let prior = ["a", "b", "c"]
        let result = RecentSearchesStore.recording("new", into: prior, cap: 2)
        XCTAssertEqual(result, ["new", "a"])
    }

    // MARK: - recording: whitespace handling

    func testRecordingIgnoresWhitespaceOnly() {
        let prior = ["Asprilla"]
        XCTAssertEqual(
            RecentSearchesStore.recording("   ", into: prior),
            prior
        )
        XCTAssertEqual(
            RecentSearchesStore.recording("\n\t  ", into: prior),
            prior
        )
    }

    func testRecordingTrimsLeadingAndTrailingWhitespace() {
        let result = RecentSearchesStore.recording("  Asprilla  ", into: [])
        XCTAssertEqual(result, ["Asprilla"])
    }

    func testRecordingPreservesInternalWhitespace() {
        let result = RecentSearchesStore.recording("social license", into: [])
        XCTAssertEqual(result, ["social license"])
    }

    // MARK: - recording: empty input

    func testRecordingEmptyStringNoOp() {
        let prior = ["Asprilla"]
        XCTAssertEqual(RecentSearchesStore.recording("", into: prior), prior)
    }
}
