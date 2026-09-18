@testable import Fichero
import Foundation
import Testing

/// spec: panes-workspaces §F7 — the pure pane-list model that replaces
/// WidescreenPanePlan's four Bools. These pin the composition contracts the F7
/// reliability + composability rely on, off-view.
struct PaneListTests {

    // MARK: - toggling (the reliability contract: a toggle ALWAYS changes the list)

    @Test("toggling a kind that's absent appends it")
    func toggleAbsentAppends() {
        let list = PaneList([.leaf(.library)])
        let toggled = list.toggling(.preview)
        #expect(!list.containsTopLevelLeaf(of: .preview))
        #expect(toggled.containsTopLevelLeaf(of: .preview))
        #expect(toggled.kinds == [.library, .preview])
    }

    @Test("toggling a kind that's present removes it")
    func togglePresentRemoves() {
        let list = PaneList([.leaf(.library), .leaf(.preview)])
        let toggled = list.toggling(.preview)
        #expect(!toggled.containsTopLevelLeaf(of: .preview))
        #expect(toggled.kinds == [.library])
    }

    @Test("toggling the same kind twice restores the original kind set")
    func toggleTwiceRoundTrips() {
        let list = PaneList([.leaf(.library)])
        let back = list.toggling(.reading).toggling(.reading)
        #expect(back.kinds == list.kinds)
    }

    @Test("a toggle never leaves the kind set unchanged (the toolbar reliability contract)")
    func toggleAlwaysChangesKinds() {
        for kind in PaneKind.allCases {
            let list = PaneList([.leaf(.library)])
            let toggled = list.toggling(kind)
            // Either added (kind now present) or removed (kind now absent) — never a no-op.
            #expect(list.containsTopLevelLeaf(of: kind) != toggled.containsTopLevelLeaf(of: kind))
        }
    }

    // `fromVisibility` and its two tests here (`visibilityFlagsControlPanesInOrder`,
    // `flippingAnyFlagChangesTheSet`) were DELETED (#4685 leftover cleanup, 2026-09-18): the
    // function's only production caller, `widescreenPaneSpecs`, was itself deleted as callerless
    // by the same cleanup. Coverage check before removing: `flippingAnyFlagChangesTheSet` pinned
    // "flipping any single flag always changes the visible set" — that invariant is INDEPENDENTLY
    // covered against the LIVE mechanism by `toggleAlwaysChangesKinds` above (`.toggling(_:)`, not
    // `fromVisibility`), so it isn't lost. `visibilityFlagsControlPanesInOrder`'s other two
    // assertions (leading→trailing construction order; all-flags-false yields an EMPTY list) were
    // properties of `fromVisibility`'s own one-shot constructor, not of the live model:
    // `settingVisible` — the mechanism every current toggle path actually uses — does the
    // opposite of that second one on purpose (it REFUSES a change that would empty the list, the
    // #1696 invariant), so there is no live equivalent to re-express; nothing here needed porting.

    // MARK: - scope (different libraries / previews side by side)

    @Test("two preview leaves with different scopes coexist")
    func sameKindDifferentScopesCoexist() {
        let scopeA = PaneScope(libraryId: "lib-A")
        let scopeB = PaneScope(libraryId: "lib-B")
        let list = PaneList([.leaf(.preview, scope: scopeA), .leaf(.preview, scope: scopeB)])
        // Two of a kind is representable — impossible in the four-Bool model.
        #expect(list.nodes.count == 2)
        #expect(list.kinds == [.preview])
        #expect(scopeA != scopeB)
        #expect(scopeA.isPinned && scopeB.isPinned)
        #expect(PaneScope.current.isPinned == false)
    }

    // MARK: - asymmetric split (2 over 1)

    @Test("an asymmetric 2-over-1 nesting flattens to three leaves")
    func asymmetricSplitLeafCount() {
        // 2 over 1: a vertical split of [ a horizontal split of [a, b], c ].
        let node = PaneNode.split(.vertical, [
            .split(.horizontal, [.leaf(.preview), .leaf(.preview)]),
            .leaf(.reading)
        ])
        #expect(node.leafCount == 3)
        #expect(node.kinds == [.preview, .reading])
    }

    // The `forLayout` suite was deleted with the API it described (#4683): the pre-workspace
    // renderer derived a PaneList from the legacy visibility plan, and that path became
    // unreachable once a workspace is always applied. The behaviour those tests pinned now lives
    // in the BuiltInWorkspaceLayout compositions; `fromVisibility` (its own would-be coverage)
    // was deleted too, as callerless, #4685 leftover cleanup, 2026-09-18 — see the note above.

    // MARK: - per-instance split / close (the isolation fix, spec CD 2026-09-15)

    @Test("closing a pane removes ONLY that pane — its siblings survive (panes.close.this-pane-only)")
    func closingKeepsSiblings() {
        let paneA = UUID(); let paneB = UUID()
        let list = PaneList([
            .leaf(id: paneA, kind: .preview, scope: .current, config: .none),
            .leaf(id: paneB, kind: .preview, scope: .current, config: .none)
        ])
        let after = list.removingLeaf(paneA)
        #expect(after.nodes.count == 1)
        #expect(after.nodes.first?.id == paneB)  // the other preview is untouched, not dropped
    }

    @Test("closing a pane in a split collapses to the survivor — the row does not disappear")
    func closingCollapsesSingletonSplit() {
        let lib = UUID(); let prev = UUID()
        let list = PaneList([
            .split(.vertical, [
                .leaf(id: lib, kind: .library, scope: .current, config: .none),
                .leaf(id: prev, kind: .preview, scope: .current, config: .none)
            ])
        ])
        let after = list.removingLeaf(prev)
        #expect(after.nodes.count == 1)
        #expect(after.nodes.first?.id == lib)   // survivor promoted, whole row NOT closed
        #expect(after.kinds == [.library])
    }

    @Test("splitting a pane splits ONLY that pane; the others are untouched (panes.split.focused-only)")
    func splittingLeavesOthersUntouched() {
        let paneA = UUID(); let paneB = UUID(); let paneC = UUID()
        let list = PaneList([
            .leaf(id: paneA, kind: .library, scope: .current, config: .none),
            .leaf(id: paneB, kind: .preview, scope: .current, config: .none),
            .leaf(id: paneC, kind: .reading, scope: .current, config: .none)
        ])
        let after = list.splittingLeaf(paneB, axis: .horizontal)
        #expect(after.nodes.count == 3)
        #expect(after.nodes[0].id == paneA)     // library untouched
        #expect(after.nodes[2].id == paneC)     // reader untouched
        guard case let .split(_, axis, children) = after.nodes[1] else {
            Issue.record("the split target should now be a split"); return
        }
        #expect(axis == .horizontal)
        #expect(children.count == 2)
        #expect(children.allSatisfy { $0.kinds == [.preview] })
        #expect(after.nodes.reduce(0) { $0 + $1.leafCount } == 4)  // exactly one more pane
    }

    @Test("removing or splitting an id that isn't present is a no-op")
    func missingIdIsNoOp() {
        let list = PaneList([.leaf(.library), .leaf(.preview)])
        #expect(list.removingLeaf(UUID()).kinds == list.kinds)
        #expect(list.splittingLeaf(UUID(), axis: .vertical).kinds == list.kinds)
    }

    // MARK: - Codable (a saved workspace IS a PaneList)

    @Test("a pane list round-trips through JSON identically (workspace persistence)")
    func codableRoundTrip() throws {
        let list = PaneList([
            .leaf(.library, scope: PaneScope(libraryId: "L", folderId: "F")),
            .split(.horizontal, [.leaf(.preview), .leaf(.reading)])
        ])
        let data = try JSONEncoder().encode(list)
        let decoded = try JSONDecoder().decode(PaneList.self, from: data)
        #expect(decoded == list)
    }

    // MARK: - Per-pane config (v2 workspaces: a leaf carries presentation)

    @Test("an unconfigured pane reports isConfigured == false and stays behaviourally default")
    func unconfiguredPaneIsDefault() {
        #expect(PaneConfig.none.isConfigured == false)
        // The convenience leaf carries no override.
        if case let .leaf(_, _, _, config) = PaneNode.leaf(.library) {
            #expect(config == .none)
        } else {
            Issue.record("leaf(.library) should be a leaf")
        }
    }

    @Test("a configured leaf (claims-as-table, word-box preview) round-trips through JSON")
    func configuredLeavesRoundTrip() throws {
        let list = PaneList([
            .leaf(.library, config: PaneConfig(libraryContentKind: "claims", libraryLayout: "table")),
            .leaf(.preview, config: PaneConfig(previewLens: "preview", previewWordBoxes: true))
        ])
        let decoded = try JSONDecoder().decode(PaneList.self, from: JSONEncoder().encode(list))
        #expect(decoded == list)
        // The presentation survived, not just the kinds.
        if case let .leaf(_, _, _, config) = decoded.nodes[0] {
            #expect(config.libraryContentKind == "claims")
            #expect(config.libraryLayout == "table")
            #expect(config.isConfigured)
        } else {
            Issue.record("first node should be a configured library leaf")
        }
    }
}
