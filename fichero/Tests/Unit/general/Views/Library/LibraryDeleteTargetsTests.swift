@testable import Fichero
import XCTest

/// #2501 — the Finder-semantics delete-target resolution shared by the row
/// context menu and the iOS swipe-to-delete action. Both must resolve the SAME
/// targets and feed the same confirm dialog → audited `document.delete` action.
final class LibraryDeleteTargetsTests: XCTestCase {

    private func doc(_ id: String) -> Document {
        Document(id: id, name: id)
    }

    /// Acting on a row OUTSIDE the selection deletes only that row — the
    /// bystander selection is untouched.
    func testUnselectedRowDeletesOnlyItself() {
        let targets = LibraryView.deleteTargets(
            for: doc("b"),
            selection: ["a", "c"],
            visibleDocuments: [doc("a"), doc("b"), doc("c")]
        )
        XCTAssertEqual(targets.map(\.id), ["b"])
    }

    /// Acting on a row INSIDE the selection deletes the whole visible
    /// selection, in visible order (Finder semantics).
    func testSelectedRowDeletesWholeSelectionInVisibleOrder() {
        let targets = LibraryView.deleteTargets(
            for: doc("c"),
            selection: ["c", "a"],
            visibleDocuments: [doc("a"), doc("b"), doc("c")]
        )
        XCTAssertEqual(targets.map(\.id), ["a", "c"])
    }

    /// Selected ids that are no longer visible (filtered out, child outline
    /// rows) are NOT deleted — only visible documents resolve.
    func testHiddenSelectionMembersAreExcluded() {
        let targets = LibraryView.deleteTargets(
            for: doc("a"),
            selection: ["a", "ghost", "a:page:1"],
            visibleDocuments: [doc("a"), doc("b")]
        )
        XCTAssertEqual(targets.map(\.id), ["a"])
    }

    /// Empty selection: the acted-on row alone.
    func testEmptySelectionDeletesActedRow() {
        let targets = LibraryView.deleteTargets(
            for: doc("solo"),
            selection: [],
            visibleDocuments: [doc("solo")]
        )
        XCTAssertEqual(targets.map(\.id), ["solo"])
    }

    /// Degenerate guard case: the acted-on row is selected but nothing in the
    /// selection is visible — resolves empty, and promptDelete presents
    /// nothing (its guard). No silent wrong-target delete.
    func testSelectedButNothingVisibleResolvesEmpty() {
        let targets = LibraryView.deleteTargets(
            for: doc("a"),
            selection: ["a"],
            visibleDocuments: []
        )
        XCTAssertTrue(targets.isEmpty)
    }
}
