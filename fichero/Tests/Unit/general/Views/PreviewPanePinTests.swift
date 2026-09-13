@testable import Fichero
import XCTest

/// F3 (panes-magnifiers-workspaces spec): the preview pane's pin must resolve
/// PER split half, so pinning one half of a split preview does not pin the
/// other. The pin now lives as `@State` inside `PreviewSplitPaneHost` (one per
/// SplittablePane sub-instance), and the pin DECISION — pinned snapshot wins
/// over the live selection — is the pure `PreviewPanePin` seam these tests
/// exercise without a running view.
///
/// This is a behaviour test of the resolution rule, NOT a source scrape: it
/// proves that two hosts holding different pin state resolve to different
/// documents from the same live selection, which is exactly what makes the two
/// split halves independent.
final class PreviewPanePinTests: XCTestCase {

    private let live = Document(id: "live", name: "Live Selection.pdf")
    private let snapshotA = Document(id: "snap-a", name: "Pinned A.pdf")
    private let snapshotB = Document(id: "snap-b", name: "Pinned B.pdf")

    // MARK: - effectiveDocument

    func testPinnedSnapshotWinsOverLiveSelection() {
        let shown = PreviewPanePin.effectiveDocument(pinned: snapshotA, live: live)
        XCTAssertEqual(shown?.id, snapshotA.id,
                       "A pinned pane must freeze on its snapshot, not follow the live selection.")
    }

    func testUnpinnedFollowsLiveSelection() {
        let shown = PreviewPanePin.effectiveDocument(pinned: nil, live: live)
        XCTAssertEqual(shown?.id, live.id,
                       "An unpinned pane must show the live selection.")
    }

    func testUnpinnedWithNoLiveSelectionResolvesToNothing() {
        XCTAssertNil(PreviewPanePin.effectiveDocument(pinned: nil, live: nil))
    }

    // MARK: - Independence of two split halves (the F3 bug)

    /// The regression this fixes: splitting a preview and pinning one half used
    /// to pin BOTH, because the pin lived on the single ContentView above the
    /// split. With per-instance pin state, two halves fed the SAME live
    /// selection resolve to DIFFERENT documents when their pins differ.
    func testTwoHalvesWithDifferentPinStateResolveIndependently() {
        // Left half pinned to A, right half unpinned — same live selection.
        let leftShown = PreviewPanePin.effectiveDocument(pinned: snapshotA, live: live)
        let rightShown = PreviewPanePin.effectiveDocument(pinned: nil, live: live)

        XCTAssertEqual(leftShown?.id, snapshotA.id)
        XCTAssertEqual(rightShown?.id, live.id)
        XCTAssertNotEqual(leftShown?.id, rightShown?.id,
                          "Two split halves with different pin state must resolve to different documents.")
    }

    /// Both halves pinned, but to DIFFERENT snapshots — still independent.
    func testTwoHalvesPinnedToDifferentSnapshots() {
        let leftShown = PreviewPanePin.effectiveDocument(pinned: snapshotA, live: live)
        let rightShown = PreviewPanePin.effectiveDocument(pinned: snapshotB, live: live)

        XCTAssertEqual(leftShown?.id, snapshotA.id)
        XCTAssertEqual(rightShown?.id, snapshotB.id)
        XCTAssertNotEqual(leftShown?.id, rightShown?.id)
    }

    // MARK: - isPinned

    func testIsPinnedReflectsSnapshotPresence() {
        XCTAssertTrue(PreviewPanePin.isPinned(pinned: snapshotA))
        XCTAssertFalse(PreviewPanePin.isPinned(pinned: nil))
    }
}
