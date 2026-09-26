@testable import Fichero
import Foundation
import Testing

/// source-model panes recon, slices A/B (#4967/#4878/#4976, 2026-09-20): identity-preserving
/// pane operations. Split out of `PaneListTests.swift` (already over the lint size limits) —
/// same suite's contract, a separate file so neither grows past the limit.
struct PaneListIdentityTests {

    /// The ONE CODE PATH ruling's own test (slice A, #4967): `splittingLeavesOthersUntouched`
    /// (in `PaneListTests.swift`) already pins a SINGLE split; this pins that the same isolation
    /// holds when the tree is ALREADY split and the SECOND split lands on one of the two
    /// children — the exact repro shape ("split a pane, then split ONE of the two resulting
    /// panes"). Split out of a single, longer test (was `splittingAnAlreadySplitPairThenChangingOneChildsKindIsIsolated`)
    /// so each half stays under the function-body lint limit — `changingTheDuplicatesKindAfterASecondSplitIsIsolated`
    /// below continues from this one's own result shape, not a fresh tree, so the repro stays
    /// exactly "split, then split again, then change kind."
    @Test("splitting one leaf of an already-split pair, in each direction, leaves every other leaf untouched and the leaf count rises by exactly one")
    func splittingAnAlreadySplitPairLeavesTheOtherHalfUntouched() {
        for axis in [SplitAxis.horizontal, .vertical] {
            let (afterSplit, paneA, paneB) = Self.splitOneHalfOfAnAlreadySplitPair(axis: axis)
            #expect(
                afterSplit.leafCount == 3,
                Comment(rawValue: "splitting one already-split half (axis \(axis)) must add exactly one pane")
            )

            guard case let .split(_, _, outerChildren) = afterSplit.nodes[0] else {
                Issue.record("expected the outer split to survive"); continue
            }
            guard case let .leaf(idA, kindA, _, _) = outerChildren[0] else {
                Issue.record("expected leaf A first, untouched"); continue
            }
            #expect(idA == paneA)
            #expect(kindA == .library)

            guard case let .split(_, innerAxis, innerChildren) = outerChildren[1] else {
                Issue.record("expected B's position to now be its own split"); continue
            }
            #expect(innerAxis == axis)
            #expect(innerChildren.count == 2)
            guard case let .leaf(bOriginalId, bOriginalKind, _, _) = innerChildren[0] else {
                Issue.record("expected B's original leaf first"); continue
            }
            #expect(bOriginalId == paneB)
            #expect(bOriginalKind == .preview)
            guard case let .leaf(bNewId, bNewKind, _, _) = innerChildren[1] else {
                Issue.record("expected B's fresh duplicate second"); continue
            }
            #expect(bNewKind == .preview)
            #expect(bNewId != paneB, "the duplicate must be a genuinely NEW leaf id, not a second view of the same leaf")
        }
    }

    /// The second half (#4878's shape): after the already-split pair is split again, changing
    /// the KIND of only the fresh duplicate must leave leaf A and B's ORIGINAL leaf untouched.
    @Test("changing the kind of a duplicate created by splitting an already-split pair leaves the original half and the other top-level pane untouched")
    func changingTheDuplicatesKindAfterASecondSplitIsIsolated() {
        for axis in [SplitAxis.horizontal, .vertical] {
            let (afterSplit, paneA, paneB) = Self.splitOneHalfOfAnAlreadySplitPair(axis: axis)
            guard case let .split(_, _, outerChildren) = afterSplit.nodes[0],
                  case let .split(_, _, innerChildren) = outerChildren[1],
                  case let .leaf(bNewId, _, _, _) = innerChildren[1] else {
                Issue.record("expected the split-of-a-split shape from the setup helper"); continue
            }

            let afterKindChange = afterSplit.changingLeafKind(bNewId, to: .reading)
            #expect(afterKindChange.leafCount == 3)
            guard case let .split(_, _, outerChildren2) = afterKindChange.nodes[0] else {
                Issue.record("expected the outer split to survive the kind change"); continue
            }
            guard case let .leaf(idA2, kindA2, _, _) = outerChildren2[0] else {
                Issue.record("expected leaf A still first, still untouched"); continue
            }
            #expect(idA2 == paneA)
            #expect(kindA2 == .library, "A must be untouched by a kind change addressed to B's duplicate")
            guard case let .split(_, _, innerChildren2) = outerChildren2[1] else {
                Issue.record("expected B's split to survive"); continue
            }
            guard case let .leaf(bOriginalId2, bOriginalKind2, _, _) = innerChildren2[0] else {
                Issue.record("expected B's original leaf still first"); continue
            }
            #expect(bOriginalId2 == paneB)
            #expect(
                bOriginalKind2 == .preview,
                "B's ORIGINAL leaf must keep its kind — only its duplicate was targeted"
            )
            guard case let .leaf(bNewId2, bNewKind2, _, _) = innerChildren2[1] else {
                Issue.record("expected the duplicate still second"); continue
            }
            #expect(bNewId2 == bNewId)
            #expect(bNewKind2 == .reading, "the targeted duplicate's kind actually changed")
        }
    }

    /// Shared setup: A and B already split side by side (the starting shape of #4967's repro,
    /// "split a pane"), then B is split again along `axis`.
    private static func splitOneHalfOfAnAlreadySplitPair(
        axis: SplitAxis
    ) -> (afterSplit: PaneList, paneA: UUID, paneB: UUID) {
        let paneA = UUID()
        let paneB = UUID()
        let list = PaneList([
            .split(.horizontal, [
                .leaf(id: paneA, kind: .library, scope: .current, config: .none),
                .leaf(id: paneB, kind: .preview, scope: .current, config: .none)
            ])
        ])
        return (list.splittingLeaf(paneB, axis: axis), paneA, paneB)
    }
}
