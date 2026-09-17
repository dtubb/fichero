@testable import Fichero
import XCTest

/// F3 (spec: panes-workspaces): the library pane's pin must resolve
/// PER split half, so pinning one half of a split library does not pin the
/// other. The pin now lives as `@State` inside `LibrarySplitPaneHost` (one per
/// SplittablePane sub-instance), and both the pin DECISION (pinned snapshot
/// wins over the live selection) and the cross-cutting RESET (a bumped clear
/// token releases a pin) are the pure `LibraryPanePin` seam these tests
/// exercise without a running view.
///
/// Behaviour test of the resolution + reset rules, NOT a source scrape: it
/// proves two hosts holding different pin state resolve to different scopes
/// from the same live selection (independent split halves), and that advancing
/// the reset token clears a pin.
final class LibraryPanePinTests: XCTestCase {

    private let liveDocs = [Document(id: "l1", name: "Live 1"), Document(id: "l2", name: "Live 2")]
    private let liveFolder: String? = "live-folder"

    private let snapshotA = PinnedLibraryScope(
        documents: [Document(id: "a1", name: "Pinned A")],
        folderId: "folder-a"
    )
    private let snapshotB = PinnedLibraryScope(
        documents: [Document(id: "b1", name: "Pinned B"), Document(id: "b2", name: "Pinned B2")],
        folderId: "folder-b"
    )

    // MARK: - effectiveDocuments / effectiveFolderId

    func testPinnedSnapshotWinsOverLiveSelection() {
        let docs = LibraryPanePin.effectiveDocuments(pinned: snapshotA, live: liveDocs)
        let folder = LibraryPanePin.effectiveFolderId(pinned: snapshotA, live: liveFolder)
        XCTAssertEqual(docs.map(\.id), ["a1"], "A pinned pane freezes on its snapshot rows.")
        XCTAssertEqual(folder, "folder-a", "A pinned pane freezes on its snapshot folder.")
    }

    func testUnpinnedFollowsLiveSelection() {
        let docs = LibraryPanePin.effectiveDocuments(pinned: nil, live: liveDocs)
        let folder = LibraryPanePin.effectiveFolderId(pinned: nil, live: liveFolder)
        XCTAssertEqual(docs.map(\.id), ["l1", "l2"], "An unpinned pane shows the live rows.")
        XCTAssertEqual(folder, "live-folder", "An unpinned pane shows the live folder.")
    }

    // MARK: - Independence of two split halves (the F3 bug)

    /// The regression this fixes: splitting a library and pinning one half used
    /// to pin BOTH, because the pin lived on the single ContentView above the
    /// split. With per-instance pin state, two halves fed the SAME live
    /// selection resolve to DIFFERENT scopes when their pins differ.
    func testTwoHalvesWithDifferentPinStateResolveIndependently() {
        let leftDocs = LibraryPanePin.effectiveDocuments(pinned: snapshotA, live: liveDocs)
        let rightDocs = LibraryPanePin.effectiveDocuments(pinned: nil, live: liveDocs)

        XCTAssertEqual(leftDocs.map(\.id), ["a1"])
        XCTAssertEqual(rightDocs.map(\.id), ["l1", "l2"])
        XCTAssertNotEqual(leftDocs.map(\.id), rightDocs.map(\.id),
                          "Two split halves with different pin state must resolve to different scopes.")
    }

    /// Both halves pinned, but to DIFFERENT snapshots — still independent.
    func testTwoHalvesPinnedToDifferentSnapshots() {
        let leftDocs = LibraryPanePin.effectiveDocuments(pinned: snapshotA, live: liveDocs)
        let rightDocs = LibraryPanePin.effectiveDocuments(pinned: snapshotB, live: liveDocs)
        XCTAssertEqual(leftDocs.map(\.id), ["a1"])
        XCTAssertEqual(rightDocs.map(\.id), ["b1", "b2"])
        XCTAssertNotEqual(
            LibraryPanePin.effectiveFolderId(pinned: snapshotA, live: liveFolder),
            LibraryPanePin.effectiveFolderId(pinned: snapshotB, live: liveFolder)
        )
    }

    // MARK: - isPinned

    func testIsPinnedReflectsSnapshotPresence() {
        XCTAssertTrue(LibraryPanePin.isPinned(pinned: snapshotA))
        XCTAssertFalse(LibraryPanePin.isPinned(pinned: nil))
    }

    // MARK: - Reset channel (new-search clear)

    func testAdvancingClearTokenClearsPin() {
        // A host that last saw token 3 sees a new search bump it to 4 → clear.
        XCTAssertTrue(LibraryPanePin.shouldClear(lastSeenToken: 3, currentToken: 4))
    }

    func testUnchangedClearTokenLeavesPinAlone() {
        // No new search since this half last synced → the pin survives.
        XCTAssertFalse(LibraryPanePin.shouldClear(lastSeenToken: 4, currentToken: 4))
    }
}
