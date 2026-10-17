@testable import Fichero
import XCTest

/// #5011 (`panes.split.peers-open-even`): a split takes the PLACE of the leaf it replaces, size included. Its two
/// halves open as even peers with no sizing of their own; the leaf's share in its parent moves to the split.
/// What breaks without it: both halves copy the leaf's fraction (0.4 of a row's width reused as 0.4 of a column's
/// height), nothing flexes evenly, and the column loses its width share.
final class PaneSplitKeepsShareTests: XCTestCase {
    private func split(_ config: PaneConfig, axis: SplitAxis = .vertical) throws -> (PaneNode, PaneNode, PaneNode) {
        let leaf = PaneNode.leaf(.library, config: config)
        let result = leaf.splittingLeaf(leaf.id, axis: axis)
        guard case let .split(_, _, halves) = result, halves.count == 2,
              case .leaf = halves[0], case .leaf = halves[1] else {
            XCTFail("a leaf splits into two leaves")
            throw CancellationError()
        }
        return (result, halves[0], halves[1])
    }

    private func config(_ node: PaneNode) -> PaneConfig {
        guard case let .leaf(_, _, _, config) = node else { return .none }
        return config
    }

    func testHalvesOpenWithNoSizingOfTheirOwn() throws {
        let (_, first, second) = try split(PaneConfig(paneFraction: 0.4))
        XCTAssertNil(config(first).paneFraction)
        XCTAssertNil(config(second).paneFraction)
        XCTAssertNil(config(second).splitFraction, "only the first half carries the split's share")
    }

    func testTheSplitKeepsTheLeafsShareInItsParent() throws {
        let (result, first, _) = try split(PaneConfig(paneFraction: 0.4))
        XCTAssertEqual(config(first).splitFraction, 0.4)
        XCTAssertEqual(result.firstLeaf.map(config)?.splitFraction, 0.4, "a split's share is read from its first leaf")
    }

    func testAFilmStripExtentMovesTheSameWay() throws {
        let (_, first, second) = try split(PaneConfig(paneExtent: 72))
        XCTAssertEqual(config(first).splitExtent, 72)
        XCTAssertNil(config(first).paneExtent)
        XCTAssertNil(config(second).paneExtent)
    }

    func testASecondSplitOfTheFirstHalfKeepsTheOriginalShare() throws {
        let (outer, first, _) = try split(PaneConfig(paneFraction: 0.4))
        let again = outer.splittingLeaf(first.id, axis: .horizontal)
        XCTAssertEqual(again.firstLeaf.map(config)?.splitFraction, 0.4, "the share survives a nested split")
    }

    func testHalvesShareEvenlyAndFillTheSplit() throws {
        let (_, first, second) = try split(PaneConfig(paneFraction: 0.4))
        let sizings = ContentView.childSizings(
            [first, second].map { WorkspaceSplitStack.Sizing.preferred(extent: nil, fraction: config($0).paneFraction) },
            fallbackFraction: 0.4)
        XCTAssertEqual(sizings.count, 2)
        guard case let .fraction(share) = sizings[0], case .flex = sizings[1] else {
            return XCTFail("one even peer share and one flexing peer fill the split: \(sizings)")
        }
        XCTAssertEqual(share, 0.5, accuracy: 0.0001)
    }
}
