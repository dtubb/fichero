@testable import Fichero
import Foundation
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
}
