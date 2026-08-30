import XCTest
@testable import Fichero

/// Guardrail for #4453 — a restored selection must not name something that no
/// longer exists.
///
/// Deleting the selected sidebar item persisted its id and crash-looped the next
/// launch: `savePersistedState`'s `?? sidebarSelectionId(for:itemId:)` fallback
/// resurrected the deleted id from a stale `viewMode`, and `restorePersistedState`
/// assigned it straight back with no existence check.
///
/// The fix validates at the RESTORE boundary rather than at the delete site,
/// because the delete site can only clear the window that performed it. There are
/// two paths that restore an id — scene storage, and a `WindowSeed` from
/// Duplicate Window — and they meet at the same `selectedSidebarItem` storage, so
/// one check covers both. A fix at the delete site would look right, pass its own
/// test, and leave Duplicate Window carrying a deleted id into a fresh window that
/// never saw the deletion.
///
/// These tests pin the PREDICATE that decides it. Driving a real window from a
/// seed needs a host; what is checkable purely is "did the restore resolve the
/// stored item, or not", which is the whole basis for dropping the selection.
final class ContentViewRestoredSelectionTests: XCTestCase {

    /// The dangling case: an id WAS stored, and the restore could not resolve it.
    func testUnresolvedItemWithStoredIdIsDangling() {
        XCTAssertTrue(
            ContentView.viewModeLostItsItem(.library(nil), storedItemId: "doc-that-was-deleted"),
            "A stored library item that no longer resolves must count as dangling (#4453)."
        )
        XCTAssertTrue(
            ContentView.viewModeLostItsItem(.chat(nil), storedItemId: "conversation-gone")
        )
        XCTAssertTrue(
            ContentView.viewModeLostItsItem(.workflow(nil), storedItemId: "workflow-gone")
        )
    }

    /// "Nothing was selected" is NOT a loss. Without this guard every fresh
    /// launch would look like a dangling selection and clear state it should
    /// have kept.
    func testNoStoredIdIsNeverDangling() {
        XCTAssertFalse(ContentView.viewModeLostItsItem(.library(nil), storedItemId: nil))
        XCTAssertFalse(ContentView.viewModeLostItsItem(.library(nil), storedItemId: ""))
        XCTAssertFalse(ContentView.viewModeLostItsItem(.chat(nil), storedItemId: nil))
    }

    /// A mode that carries no item cannot dangle, even with an id stored
    /// alongside it — dropping the selection there would be a false positive.
    func testItemlessModesAreNeverDangling() {
        XCTAssertFalse(ContentView.viewModeLostItsItem(.automation, storedItemId: "anything"))
        XCTAssertFalse(ContentView.viewModeLostItsItem(.batches, storedItemId: "anything"))
    }

    /// Not covered here: the RESOLVED case (a mode whose payload is present must
    /// report false), which needs a `Document`/`Conversation`/`Workflow` fixture
    /// and a host to build one meaningfully. The predicate returns false for any
    /// non-nil payload by construction — `document == nil` — so the risk is low,
    /// but it is an assertion this file does not make and should not be read as
    /// making.
    func testResolvedCaseIsNotCoveredHere() throws {
        throw XCTSkip("Resolved-payload case needs a model fixture; see the note above (#4453).")
    }
}
