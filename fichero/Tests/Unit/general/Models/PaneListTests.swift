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

    // The slice-A "split an already-split pair, then change one child's kind" test
    // (#4967/#4878) moved to `PaneListIdentityTests.swift` (2026-09-20, slice B/C prep):
    // this file was over the lint size limits and team-lead asked for new cases to go in
    // a new suite rather than growing this one — the long test was split into two there.

    @Test("removing or splitting an id that isn't present is a no-op")
    func missingIdIsNoOp() {
        let list = PaneList([.leaf(.library), .leaf(.preview)])
        #expect(list.removingLeaf(UUID()).kinds == list.kinds)
        #expect(list.splittingLeaf(UUID(), axis: .vertical).kinds == list.kinds)
    }

    // MARK: - Per-pane content kind (#4884: kg.tables.pane-kind-mismatch)

    /// finding C7's neighbour — the "one leaf only" contract `changingLeafKind`
    /// already gives pane-KIND switches must hold for CONTENT-kind switches too,
    /// nested inside a split, not just at the top level.
    @Test("changing one leaf's content kind touches ONLY that leaf, even nested in a split")
    func changingContentKindLeavesOthersUntouched() {
        let libA = UUID(); let libB = UUID()
        let list = PaneList([
            .split(.vertical, [
                .leaf(id: libA, kind: .library, scope: .current, config: PaneConfig(libraryContentKind: "claims")),
                .leaf(id: libB, kind: .library, scope: .current, config: .none)
            ])
        ])
        let after = list.changingLeafContentKind(libA, to: "entities")
        guard case let .split(_, _, children) = after.nodes[0] else {
            Issue.record("expected the split to survive"); return
        }
        guard case let .leaf(_, _, _, configA) = children[0] else {
            Issue.record("expected leaf A"); return
        }
        guard case let .leaf(_, _, _, configB) = children[1] else {
            Issue.record("expected leaf B"); return
        }
        #expect(configA.libraryContentKind == "entities")  // changed
        #expect(configB.libraryContentKind == nil)         // the OTHER library pane untouched
    }

    @Test("clearing a leaf's content kind (nil) goes back to following the window")
    func changingContentKindToNilClears() {
        let leaf = UUID()
        let list = PaneList([
            .leaf(id: leaf, kind: .library, scope: .current, config: PaneConfig(libraryContentKind: "claims"))
        ])
        let after = list.changingLeafContentKind(leaf, to: nil)
        guard case let .leaf(_, _, _, config) = after.nodes[0] else {
            Issue.record("expected a leaf"); return
        }
        #expect(config.libraryContentKind == nil)
    }

    @Test("changing a content kind that isn't present is a no-op")
    func changingContentKindMissingIdIsNoOp() {
        let list = PaneList([.leaf(.library, config: PaneConfig(libraryContentKind: "claims"))])
        let after = list.changingLeafContentKind(UUID(), to: "entities")
        #expect(after == list)
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

    /// #4884 ruling (5): an OLD saved workspace, written before `libraryContentKind`
    /// existed as a written field, must decode to `nil` for it — never fail to
    /// decode, never default to some non-nil kind that would silently override
    /// the window for every pane in an old save. Simulated the honest way: a
    /// config that never SET `libraryContentKind` encodes with no key for it at
    /// all (synthesized `Codable` on an `Optional` property omits a `nil` value
    /// entirely, via `encodeIfPresent`) — first assert that, proving the JSON
    /// this test decodes really is what a pre-#4884 save looks like, not a
    /// guessed shape.
    @Test("an old saved workspace with no libraryContentKind key decodes to nil, not a crash or a default")
    func oldWorkspaceWithoutContentKindDecodesToNil() throws {
        let preExisting = PaneList([.leaf(.library, config: PaneConfig(libraryLayout: "table"))])
        let data = try JSONEncoder().encode(preExisting)
        let json = try #require(String(data: data, encoding: .utf8))
        #expect(
            !json.contains("libraryContentKind"),
            "this JSON is meant to simulate a pre-#4884 save — it must not already carry the key"
        )

        let decoded = try JSONDecoder().decode(PaneList.self, from: data)
        guard case let .leaf(_, _, _, config) = decoded.nodes[0] else {
            Issue.record("expected a leaf"); return
        }
        #expect(config.libraryContentKind == nil)
        #expect(config.libraryLayout == "table")  // the field that WAS there still decodes
    }
}
