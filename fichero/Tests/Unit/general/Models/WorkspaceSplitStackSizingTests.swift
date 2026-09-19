@testable import Fichero
import Foundation
import SwiftUI
import Testing

/// #4688 — proportional splits + the sum-clamp + workspace-unique storage keys. All PURE: no view
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

    // MARK: - Storage keys differ across workspaces at the same tree position (#4688 defect 3)

    @Test("storage keys at the same tree position differ across the five built-in workspaces")
    func storageKeysDifferAcrossWorkspaces() {
        // Read's inner split and Transcribe/Compare's film-strip split are BOTH nominally the
        // top-level "root" position — the exact collision the issue reports ("wsplit.0.0" shared
        // by Read's inner split and the film strip). Each workspace's `PaneList` carries freshly
        // generated node ids, so keying on the leading child's id (not just "root") must diverge.
        let keys = BuiltInWorkspaceLayout.allCases.map { layout in
            WorkspaceSplitStack.storageKey(keyPath: "root", leadingChildID: layout.panes.nodes.first?.id)
        }
        #expect(Set(keys).count == keys.count)
    }

    @Test("the same PaneList's storage key is stable across repeated calls")
    func storageKeyStableForOneList() {
        let list = BuiltInWorkspaceLayout.read.panes
        let first = WorkspaceSplitStack.storageKey(keyPath: "root", leadingChildID: list.nodes.first?.id)
        let second = WorkspaceSplitStack.storageKey(keyPath: "root", leadingChildID: list.nodes.first?.id)
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

    /// The un-weighted case with NO peers at all (every sibling explicit) leaves every child
    /// exactly as given — no forced flex invented where nothing is left to flex.
    @Test("with no peers, every explicit sibling keeps its own preference")
    func noPeersKeepsEveryExplicitPreference() {
        let preferences: [WorkspaceSplitStack.Sizing?] = [.fraction(0.4), .fraction(0.6)]
        let sizings = ContentView.childSizings(preferences, fallbackFraction: 0.4)
        #expect(sizings == [.fraction(0.4), .fraction(0.6)])
    }
}
