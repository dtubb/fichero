@testable import Fichero
import Foundation
import XCTest

/// Daniel's 2026-08-14 launch log carried four dead bookmarks for
/// `…/Data/tmp/FicheroTests/…` libraries: unit tests opened temp libraries
/// through the real LibraryManager, and in the TEST HOST `.standard` IS the
/// app's defaults domain — so test libraries persisted into the user's real
/// saved bookmarks and failed to restore on every launch. Transient paths
/// (container tmp) and test runs must never persist.
@MainActor
final class FolderAccessBookmarkHygieneTests: XCTestCase {
    func testTestHostNeverPersistsBookmarks() async throws {
        let defaults = UserDefaults.standard
        let key = "FolderAccessBookmarks"
        let before = (defaults.dictionary(forKey: key) as? [String: Data]) ?? [:]

        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("FicheroTests-hygiene-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }

        FolderAccessManager.shared.saveBookmark(for: dir)
        // saveBookmark's engine hand-off is async fire-and-forget; persistence
        // (the part under test) is synchronous, so no wait is needed.
        let after = (defaults.dictionary(forKey: key) as? [String: Data]) ?? [:]
        XCTAssertNil(after[dir.path], "a test-host bookmark leaked into the app's saved bookmarks")
        XCTAssertEqual(
            Set(after.keys), Set(before.keys),
            "the saved-bookmarks set must be untouched by a test run"
        )
    }
}
