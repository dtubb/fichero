@testable import Fichero
import Foundation
import SwiftUI
import Testing

/// #4688 — proportional splits + the sum-clamp + sizes that never leak between workspaces
/// (by pane id inside the stored value since #4994, not by storage key). All PURE: no view
/// mounted, no GeometryReader, no @SceneStorage. `WorkspaceSplitStack.resolvedExtents` and
/// `.storageKey` are the extracted maths/keying the fix relies on.
struct WorkspaceSplitStackSizingTests {

    // MARK: - Fractions resolve to points at several stack sizes

    @Test("a fraction resolves to fraction × total at 800/1400/2560pt")
    func fractionResolvesAcrossStackSizes() {
        for total in [800.0, 1400.0, 2560.0] {
            let resolved = WorkspaceSplitStack.resolvedExtents(
                [.fraction(0.4), .flex], total: total
            )
            #expect(resolved[0] == 0.4 * total)
            #expect(resolved[1] == nil)
        }
    }

    @Test("a fixed pin resolves to its own points regardless of total")
    func fixedResolvesToItsOwnPoints() {
        for total in [200.0, 800.0, 2560.0] {
            let resolved = WorkspaceSplitStack.resolvedExtents([.flex, .fixed(72)], total: total)
            #expect(resolved[1] == 72)
        }
    }

    // MARK: - The sum-clamp (#4688 defect 2)

    @Test("the sum of sized children never exceeds total minus the flex minimum")
    func sumNeverExceedsBudget() {
        // Two 360pt-equivalent children in a 600pt stack sum to 720 — the reported defect.
        let resolved = WorkspaceSplitStack.resolvedExtents(
            [.fixed(360), .fixed(360), .flex], total: 600, minPerPane: 48, flexMinimum: 48
        )
        let sum = resolved.compactMap { $0 }.reduce(0, +)
        #expect(sum <= 600 - 48)
    }

    @Test("a total at or below 96pt no longer passes the raw value straight through")
    func tinyTotalIsBounded() {
        let resolved = WorkspaceSplitStack.resolvedExtents([.fixed(360), .flex], total: 90, minPerPane: 48, flexMinimum: 48)
        // The old `clamp` returned 360 untouched whenever total <= 96; the sum-aware
        // replacement must still respect the stack.
        #expect(resolved[0]! <= 90)
    }

    @Test("per-pane minimum holds even when many siblings compete for a small stack")
    func perPaneMinimumHolds() {
        let resolved = WorkspaceSplitStack.resolvedExtents(
            [.fixed(300), .fraction(0.5), .flex], total: 200, minPerPane: 48, flexMinimum: 48
        )
        for value in resolved.compactMap({ $0 }) {
            #expect(value >= 48)
        }
    }

    // MARK: - An absolute extent wins over a fraction (#4688: "paneExtent wins")

    @Test("Sizing.preferred: an absolute extent wins over a fraction on the same leaf")
    func extentWinsOverFraction() {
        #expect(WorkspaceSplitStack.Sizing.preferred(extent: 72, fraction: 0.4) == .fixed(72))
    }

    @Test("Sizing.preferred: a fraction alone is used when no extent is set")
    func fractionUsedWithoutExtent() {
        #expect(WorkspaceSplitStack.Sizing.preferred(extent: nil, fraction: 0.4) == .fraction(0.4))
    }

    @Test("Sizing.preferred: neither set is nil (caller's flex/fallback decides)")
    func neitherSetIsNil() {
        #expect(WorkspaceSplitStack.Sizing.preferred(extent: nil, fraction: nil) == nil)
    }

    // MARK: - Sizes never leak between workspaces at the same tree position (#4688, #4994)

    /// Every node id (leaf and split) in a composition — a stack's children can be either.
    private func nodeIDs(of list: PaneList) -> [UUID] {
        func walk(_ node: PaneNode) -> [UUID] {
            switch node {
            case .leaf: return [node.id]
            case let .split(_, _, children): return [node.id] + children.flatMap(walk)
            }
        }
        return list.nodes.flatMap(walk)
    }

    /// The storage key is a tree POSITION and is the same for every workspace (#4994: a key that
    /// followed the workspace changed under a live `@SceneStorage`). What keeps Read's split and
    /// Transcribe's film strip — both at one position — from sharing a size is that the stored
    /// value is keyed by pane id, and no two built-in workspaces share one.
    @Test("the five built-in workspaces' pane ids are pairwise disjoint")
    func builtInPaneIDsAreDisjoint() {
        let all = BuiltInWorkspaceLayout.allCases.flatMap { nodeIDs(of: $0.panes) }
        #expect(!all.isEmpty)
        #expect(Set(all).count == all.count, "two built-in panes share an id, so they would share a stored size")
    }

    @Test("a size stored for one workspace's pane is never read by another workspace at the same position")
    func storedSizeDoesNotLeakAcrossWorkspaces() throws {
        for owner in BuiltInWorkspaceLayout.allCases {
            // One workspace drags every one of its panes; this is what its stack persists.
            let owned = nodeIDs(of: owner.panes)
            let json = try #require(WorkspaceSplitStack.encodeStoredFractions(
                Dictionary(uniqueKeysWithValues: owned.map { ($0, 0.42) })
            ))
            let stored = WorkspaceSplitStack.decodeStoredFractions(json)
            #expect(stored.count == owned.count)

            // Every OTHER workspace reads the same slot (same position, same key) by its own ids.
            for other in BuiltInWorkspaceLayout.allCases where other != owner {
                let leaked = nodeIDs(of: other.panes).filter { stored[$0] != nil }
                #expect(leaked.isEmpty, "another workspace read a size that was dragged in a different one")
            }
        }
    }

    @Test("a split's storage key does not depend on which workspace is applied")
    func storageKeyIsThePositionAlone() {
        #expect(WorkspaceSplitStack.storageKey(keyPath: "root") == "root")
        #expect(WorkspaceSplitStack.storageKey(keyPath: "0.1") == "0.1")
    }

    @Test("the same PaneList's storage key is stable across repeated calls")
    func storageKeyStableForOneList() {
        let first = WorkspaceSplitStack.storageKey(keyPath: "root")
        let second = WorkspaceSplitStack.storageKey(keyPath: "root")
        #expect(first == second)
    }

    // MARK: - #4848 panes.strip.fixed-extent-is-content-not-whole-pane

    /// The strip's pinned extent is the VISIBLE ICON STRIP plus its own chrome (head bar +
    /// bottom mini-toolbar) — not the icon strip alone, which left no room for the head/footer
    /// to render (the reported bug: no icons showed at all).
    @Test("a library strip's whole-pane extent is the icon strip plus its own chrome")
    func libraryStripExtentAddsChrome() {
        let extent = ContentView.libraryStripExtent(iconStrip: 72)
        // Both sides as Double: `extent` is a Double and the metrics are CGFloat,
        // and the #expect macro compares a Double with a CGFloat as unequal even
        // when both print 142.0.
        let expected = 72.0
            + Double(PaneHeadMetrics.barHeight)
            + Double(MiniToolbar<EmptyView, EmptyView>.standardHeight)
        #expect(extent == expected)
        // The chrome is real, not zero — a regression that stopped adding it would still pass
        // an equality-to-itself check.
        #expect(extent > 72)
    }

    // MARK: - #4849 panes.split.peers-open-even

    /// `resolvedExtents` returns `nil` for a `.flex` slot — the real value only exists once
    /// SwiftUI hands it whatever the sized siblings left over. This fills that ONE slot back in
    /// as `total − sum(the rest)`, so "peers are equal within a point" can be checked including
    /// the one peer that's actually `.flex` (mathematically the same share, by construction —
    /// `ContentView.childSizings`'s own doc comment states the identity this asserts).
    private static func effectiveExtents(_ resolved: [Double?], total: Double) -> [Double] {
        let sizedSum = resolved.compactMap { $0 }.reduce(0, +)
        let flexValue = total - sizedSum
        return resolved.map { $0 ?? flexValue }
    }

    /// n peers, none carrying an explicit weight, resolve to equal extents within a point — for
    /// 2, 3, and 4, the shape the issue names explicitly.
    @Test("2, 3, and 4 un-weighted peers resolve to equal extents")
    func peersOfEveryCountOpenEqual() {
        for peerCount in [2, 3, 4] {
            let preferences: [WorkspaceSplitStack.Sizing?] = Array(repeating: nil, count: peerCount)
            let sizings = ContentView.childSizings(preferences, fallbackFraction: 0.4)
            let resolved = WorkspaceSplitStack.resolvedExtents(sizings, total: 1200)
            let extents = Self.effectiveExtents(resolved, total: 1200)
            #expect(extents.count == peerCount)
            let expected = 1200.0 / Double(peerCount)
            for extent in extents {
                #expect(abs(extent - expected) < 1, "peer extents must be equal within a point")
            }
        }
    }

    /// A split with an explicit, deliberately-unequal weight (the narrow-Library-navigator
    /// shape the issue names) keeps that weight; the un-weighted peers beside it split ONLY
    /// what it leaves over, evenly.
    @Test("an explicit weight is kept; the remaining peers share the rest evenly")
    func mixedSplitKeepsExplicitWeightAndSharesTheRest() {
        // A narrow navigator at 0.2, three un-weighted content peers sharing the other 0.8.
        let preferences: [WorkspaceSplitStack.Sizing?] = [.fraction(0.2), nil, nil, nil]
        let sizings = ContentView.childSizings(preferences, fallbackFraction: 0.4)
        let resolved = WorkspaceSplitStack.resolvedExtents(sizings, total: 1000)
        let effective = Self.effectiveExtents(resolved, total: 1000)
        #expect(abs(effective[0] - 200) < 1, "the explicit 0.2 weight is unchanged")
        for extent in effective[1...] {
            // The three peers split the remaining 0.8 (800pt) evenly: ~266.67pt each.
            #expect(abs(extent - (800.0 / 3.0)) < 1, "peers must share only what the explicit weight leaves")
        }
    }

    /// A hard-pinned film strip plus its ONE content peer (every built-in's actual shape: the
    /// film strip's outer split always has exactly one other child, the content split) — the pin
    /// keeps its own points, the single peer flexes into everything else, exactly.
    @Test("a pin is kept; its one peer flexes into exactly what's left")
    func pinnedSplitKeepsItsPointsAndItsOnePeerFlexesExactly() {
        let preferences: [WorkspaceSplitStack.Sizing?] = [nil, .fixed(72)]
        let sizings = ContentView.childSizings(preferences, fallbackFraction: 0.4)
        let resolved = WorkspaceSplitStack.resolvedExtents(sizings, total: 1000)
        #expect(resolved[1] == 72, "the pin is unchanged")
        let effective = Self.effectiveExtents(resolved, total: 1000)
        #expect(effective[0] == 928, "the sole peer gets exactly total minus the pin")
    }

    /// KNOWN LIMITATION (documented on `childSizings`, not fixed here — not exercised by any
    /// built-in and not part of #4849's reported shape): with a pin AND more than one peer,
    /// `peerShare` cannot subtract the pin's absolute points from `total` (this pure function has
    /// no `total`), so the peers divide the WHOLE total evenly among themselves while the one
    /// flexing peer additionally absorbs the pin's points — the flexing peer ends up smaller than
    /// its non-flexing siblings by roughly the pin's size. Pinned here as the CURRENT, accepted
    /// behavior so a future change to it is a deliberate decision, not a silent drift.
    @Test("a pin with MULTIPLE peers: non-flexing peers divide the whole total, not total-minus-pin")
    func pinnedSplitWithMultiplePeersIsAKnownLimitation() throws {
        let preferences: [WorkspaceSplitStack.Sizing?] = [nil, nil, nil, .fixed(72)]
        let sizings = ContentView.childSizings(preferences, fallbackFraction: 0.4)
        let resolved = WorkspaceSplitStack.resolvedExtents(sizings, total: 1000)
        #expect(resolved[3] == 72, "the pin is unchanged")
        let effective = Self.effectiveExtents(resolved, total: 1000)
        // Non-flexing peers (indices 1, 2): 1/3 of the WHOLE total each.
        #expect(abs(effective[1] - (1000.0 / 3.0)) < 1)
        #expect(abs(effective[2] - (1000.0 / 3.0)) < 1)
        // The flexing peer (index 0) additionally absorbs the pin, so it is smaller.
        #expect(effective[0] < effective[1] - 1, "documents the limitation — this is NOT equal to its siblings")
    }

    /// A user's drag still wins over the even-peer default — the SAME `storedOverrides`
    /// precedence `panes.split.fraction-not-seeded` already pins, exercised on a peer split.
    @Test("a stored drag still wins over the even-peer default")
    func storedDragWinsOverPeerDefault() {
        let preferences: [WorkspaceSplitStack.Sizing?] = [nil, nil, nil]
        let sizings = ContentView.childSizings(preferences, fallbackFraction: 0.4)
        // Without a drag: equal thirds.
        let undragged = Self.effectiveExtents(
            WorkspaceSplitStack.resolvedExtents(sizings, total: 900), total: 900
        )
        for extent in undragged {
            #expect(abs(extent - 300) < 1)
        }
        // The first peer was dragged to 500pt; that stored value wins over its 1/3 default,
        // regardless of the total.
        let dragged = WorkspaceSplitStack.resolvedExtents(sizings, storedOverrides: [500, nil, nil], total: 900)
        #expect(dragged[0] == 500)
    }

    // MARK: - A split always has one flexing child (#5011, #5014)

    /// With no peer, the explicit shares alone used to decide the layout: two halves that each
    /// copied a 0.4 share filled 0.8 of their split and left the rest EMPTY.
    @Test("with no peers, the last child flexes so the split is always filled")
    func noPeersStillLeavesOneFlexingChild() {
        let copied: [WorkspaceSplitStack.Sizing?] = [.fraction(0.4), .fraction(0.4)]
        let sizings = ContentView.childSizings(copied, fallbackFraction: 0.4)
        #expect(sizings == [.fraction(0.4), .flex])
        let effective = Self.effectiveExtents(WorkspaceSplitStack.resolvedExtents(sizings, total: 1000), total: 1000)
        #expect(abs(effective.reduce(0, +) - 1000) < 1, "the two halves fill the whole split, no gap")
    }

    /// Closing the flexing pane of a row (Browse without its Reader) used to leave its share as a gap.
    @Test("closing the flexing pane leaves a row that still fills its width")
    func aRowWhoseFlexingPaneClosedStillFills() {
        let survivors: [WorkspaceSplitStack.Sizing?] = [.fraction(0.15), .fraction(0.60)]
        let sizings = ContentView.childSizings(survivors, fallbackFraction: 0.4)
        #expect(sizings == [.fraction(0.15), .flex])
    }

    @Test("a pin with no peer: the child that is not a pin flexes, and the pin is kept")
    func aPinWithNoPeerKeepsThePin() {
        let sizings = ContentView.childSizings([.fraction(0.5), .fixed(72)], fallbackFraction: 0.4)
        #expect(sizings == [.flex, .fixed(72)])
    }

    @Test("every child a pin (a split film strip): the last one flexes")
    func everyChildAPinStillFlexes() {
        let sizings = ContentView.childSizings([.fixed(140), .fixed(140)], fallbackFraction: 0.4)
        #expect(sizings == [.fixed(140), .flex])
    }

    @Test("every sizing decision has exactly one flexing child")
    func exactlyOneFlexingChildAlways() {
        let cases: [[WorkspaceSplitStack.Sizing?]] = [
            [nil], [nil, nil], [.fraction(0.2), nil, nil], [nil, .fixed(72)],
            [.fraction(0.4), .fraction(0.6)], [.fixed(72)], [.fixed(72), .fixed(72)],
            [.fraction(0.15), .fraction(0.60), nil],
        ]
        for preferences in cases {
            let flexing = ContentView.childSizings(preferences, fallbackFraction: 0.4).filter { $0 == .flex }
            #expect(flexing.count == 1, "one child must absorb the remainder")
        }
    }
}
