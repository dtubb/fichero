@testable import Fichero
import SwiftUI
import XCTest

final class SplittablePanePolicyTests: XCTestCase {
    func testShouldUseSplittablePaneTreatsCompactAsUnsupportedOnNonMac() {
        #if os(macOS)
        XCTAssertTrue(ContentView.shouldUseSplittablePane(horizontalSizeClass: nil))
        XCTAssertFalse(ContentView.shouldUseSplittablePane(horizontalSizeClass: .compact))
        XCTAssertTrue(ContentView.shouldUseSplittablePane(horizontalSizeClass: .regular))
        #else
        XCTAssertFalse(ContentView.shouldUseSplittablePane(horizontalSizeClass: .compact))
        XCTAssertTrue(ContentView.shouldUseSplittablePane(horizontalSizeClass: .regular))
        XCTAssertTrue(ContentView.shouldUseSplittablePane(horizontalSizeClass: nil))
        #endif
    }

    func testShouldUseSplittablePaneCollapsesWhenWindowIsTooNarrow() {
        XCTAssertFalse(
            ContentView.shouldUseSplittablePane(
                horizontalSizeClass: .regular,
                windowWidth: 599,
                minimumWidth: 600
            )
        )
        XCTAssertTrue(
            ContentView.shouldUseSplittablePane(
                horizontalSizeClass: .regular,
                windowWidth: 601,
                minimumWidth: 600
            )
        )
    }

    // MARK: - PaneModelSplitHook (ONE CODE PATH ruling, 2026-09-20, slice A)

    /// `PaneModelSplitHook.splitAxisActions()` never reports a split in
    /// progress — a further split of a pass-through `SplittablePane`
    /// produces a new SIBLING leaf in the model, not a second internal
    /// copy — so `PaneHead`'s close button always falls through to the
    /// real per-leaf close for a pane reached through this hook.
    func testModelSplitHookNeverReportsAnActiveSplit() {
        let hook = PaneModelSplitHook(split: { _ in })
        let actions = hook.splitAxisActions()
        XCTAssertFalse(actions.hasVertical)
        XCTAssertFalse(actions.hasHorizontal)
        XCTAssertEqual(actions.paneCount, 1)
    }

    /// The axis-vocabulary swap is the one trap this hook exists to get
    /// right: `SplittablePane`'s own "vertical" names a VERTICAL DIVIDER
    /// (panes side by side), which is `PaneList`'s `.horizontal` axis; its
    /// "horizontal" (stacked, a horizontal divider) is `PaneList`'s
    /// `.vertical`. Get this backwards and "Split Vertical" stacks instead
    /// of siding.
    func testModelSplitHookMapsSplittablePaneAxisVocabularyOntoPaneList() {
        var capturedAxis: SplitAxis?
        let hook = PaneModelSplitHook(split: { capturedAxis = $0 })
        let actions = hook.splitAxisActions()

        actions.onToggleVertical()
        XCTAssertEqual(capturedAxis, .horizontal, "SplittablePane 'vertical' (side-by-side) → PaneList .horizontal")

        actions.onToggleHorizontal()
        XCTAssertEqual(capturedAxis, .vertical, "SplittablePane 'horizontal' (stacked) → PaneList .vertical")
    }

    /// The end-to-end proof team-lead asked for: the in-pane split action
    /// (what `PaneChromeMenu`'s "+" ultimately calls) produces a REAL new
    /// leaf in the `PaneList` model — the same effect
    /// `PaneList.splittingLeaf` already gives the Workspaces menu — not a
    /// second rendered view of the SAME leaf, which is what `SplittablePane`
    /// did before this hook existed (#4967, #4878, #4979).
    func testInPaneSplitActionProducesANewModelLeafNotASecondViewOfTheSameOne() {
        let paneId = UUID()
        var list = PaneList([.leaf(id: paneId, kind: .reading, scope: .current, config: .none)])
        let hook = PaneModelSplitHook(split: { axis in
            list = list.splittingLeaf(paneId, axis: axis)
        })
        let actions = hook.splitAxisActions()

        XCTAssertEqual(list.leafCount, 1)
        actions.onToggleVertical()  // the "+" menu's "Split Vertical" (side-by-side)
        XCTAssertEqual(list.leafCount, 2, "the in-pane split action must add a real second leaf")

        guard case let .split(_, axis, children) = list.nodes[0] else {
            XCTFail("expected the leaf to become a split"); return
        }
        XCTAssertEqual(axis, .horizontal)  // "Split Vertical" (side-by-side) = PaneList .horizontal
        XCTAssertEqual(children.count, 2)
        guard case let .leaf(originalId, originalKind, _, _) = children[0],
              case let .leaf(duplicateId, duplicateKind, _, _) = children[1] else {
            XCTFail("expected two leaves"); return
        }
        XCTAssertEqual(originalId, paneId)
        XCTAssertEqual(originalKind, .reading)
        XCTAssertNotEqual(duplicateId, paneId, "a NEW leaf id — not the pane rendering the SAME leaf twice")
        XCTAssertEqual(duplicateKind, .reading)
    }
}
