@testable import Fichero
import XCTest

/// Covers the precomputed ⌘F search key introduced by #3865: the filter now
/// matches a lowercased `name + bounded OCR excerpt + status` key instead of
/// re-scanning every doc's full `pageContent` per keystroke.
@MainActor
final class LibraryFilterSearchKeyTests: XCTestCase {
    func testKeyIsLowercasedAndIncludesNameContentStatus() {
        let doc = Document(name: "Report ALPHA", pageContent: "The QUICK brown Fox")
        let key = LibraryView.documentSearchKey(for: doc)

        XCTAssertEqual(key, key.localizedLowercase, "key must be fully lowercased")
        XCTAssertTrue(key.contains("report alpha"), "includes the name")
        XCTAssertTrue(key.contains("quick brown fox"), "includes the OCR excerpt")
        XCTAssertTrue(key.contains(doc.status.rawValue.localizedLowercase), "includes the status")
    }

    func testKeyTruncatesOcrBeyondExcerptLimit() {
        // Fill the whole excerpt window with 'a', then a marker just past it: the
        // marker must NOT land in the key (⌘F is find-in-list, not full-text).
        let head = String(repeating: "a", count: LibraryView.searchExcerptLimit)
        let doc = Document(name: "n", pageContent: head + "NEEDLE")
        let key = LibraryView.documentSearchKey(for: doc)

        XCTAssertFalse(key.contains("needle"), "content beyond the excerpt limit is not indexed")
    }

    func testNilPageContentStillBuildsAKey() {
        let doc = Document(name: "Empty", pageContent: nil)
        let key = LibraryView.documentSearchKey(for: doc)
        XCTAssertTrue(key.contains("empty"))
    }
}
