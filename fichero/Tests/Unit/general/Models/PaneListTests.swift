@testable import Fichero
import Foundation
import Testing

/// spec: panes-magnifiers-workspaces §F7 — the pure pane-list model that replaces
/// WidescreenPanePlan's four Bools. These pin the composition contracts the F7
/// reliability + composability rely on, off-view.
struct PaneListTests {

    /// The leaf kinds of a node list, in order (splits are skipped — these helpers
    /// assert top-level composition). Keeps the pattern-match in one place.
    private func leafKinds(_ nodes: [PaneNode]) -> [PaneKind] {
        nodes.compactMap { if case let .leaf(_, kind, _, _) = $0 { return kind }; return nil }
    }

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

    // MARK: - fromVisibility (the one mode-independent derivation)

    @Test("each visibility flag independently controls its pane, in order")
    func visibilityFlagsControlPanesInOrder() {
        #expect(PaneList.fromVisibility(library: true, preview: true, reading: true, chat: true).kinds
                == [.library, .preview, .reading, .chat])
        #expect(PaneList.fromVisibility(library: false, preview: false, reading: false, chat: false).nodes.isEmpty)
        // Order is leading→trailing regardless of which are on.
        let libraryPreview = PaneList.fromVisibility(library: true, preview: true, reading: false, chat: false)
        #expect(leafKinds(libraryPreview.nodes) == [.library, .preview])
    }

    @Test("flipping ANY single flag changes the visible pane set (fixes inert toggles in every mode)")
    func flippingAnyFlagChangesTheSet() {
        // The reliability contract: because this ONE derivation is what every mode
        // uses, flipping a flag can never be a no-op (as it was in .standard/.none,
        // which read only the library flag).
        let previewOff = PaneList.fromVisibility(library: true, preview: false, reading: false, chat: false).kinds
        let previewOn = PaneList.fromVisibility(library: true, preview: true, reading: false, chat: false).kinds
        #expect(previewOn != previewOff)

        let readingOff = PaneList.fromVisibility(library: true, preview: false, reading: false, chat: false).kinds
        let readingOn = PaneList.fromVisibility(library: true, preview: false, reading: true, chat: false).kinds
        #expect(readingOn != readingOff)

        let chatOff = PaneList.fromVisibility(library: true, preview: false, reading: false, chat: false).kinds
        let chatOn = PaneList.fromVisibility(library: true, preview: false, reading: false, chat: true).kinds
        #expect(chatOn != chatOff)
    }

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

    // MARK: - forLayout (the ONE renderer: every LayoutMode composes as a PaneList)

    /// The single top-level node, or nil.
    private func onlyNode(_ list: PaneList) -> PaneNode? {
        list.nodes.count == 1 ? list.nodes.first : nil
    }

    @Test("a non-library/search mode owns the whole area as one library pane, in every mode")
    func nonLibraryModeIsOneLibraryPane() {
        for mode in [LayoutMode.none, .standard, .widescreen] {
            let list = PaneList.forLayout(
                mode: mode, showsPreview: false, showsDocumentGrid: true,
                widescreen: WidescreenVisibility(library: true, preview: true, reading: true))
            #expect(list.kinds == [.library])
            #expect(list.nodes.count == 1)
        }
    }

    @Test(".none shows library alone (grid) or preview alone (grid hidden)")
    func noneMode() {
        #expect(PaneList.forLayout(
            mode: .none, showsPreview: true, showsDocumentGrid: true,
            widescreen: WidescreenVisibility(library: false, preview: false, reading: false)).kinds == [.library])
        #expect(PaneList.forLayout(
            mode: .none, showsPreview: true, showsDocumentGrid: false,
            widescreen: WidescreenVisibility(library: false, preview: false, reading: false)).kinds == [.preview])
    }

    @Test(".standard bottom-preview is a VERTICAL split of library over preview (so it gets a pane head)")
    func standardIsVerticalSplit() {
        let list = PaneList.forLayout(
            mode: .standard, showsPreview: true, showsDocumentGrid: true,
            widescreen: WidescreenVisibility(library: false, preview: false, reading: false))
        guard case let .split(_, axis, children)? = onlyNode(list) else {
            Issue.record("standard+grid should be a single split node"); return
        }
        #expect(axis == .vertical)
        #expect(leafKinds(children) == [.library, .preview])
    }

    @Test(".standard with the grid hidden collapses to preview alone")
    func standardGridHidden() {
        let list = PaneList.forLayout(
            mode: .standard, showsPreview: true, showsDocumentGrid: false,
            widescreen: WidescreenVisibility(library: false, preview: false, reading: false))
        #expect(list.kinds == [.preview])
        #expect(list.nodes.count == 1)
    }

    @Test(".widescreen is the horizontal visibility list, in order")
    func widescreenMatchesVisibility() {
        let list = PaneList.forLayout(
            mode: .widescreen, showsPreview: true, showsDocumentGrid: true,
            widescreen: WidescreenVisibility(library: true, preview: true, reading: true))
        #expect(leafKinds(list.nodes) == [.library, .preview, .reading])
    }

    @Test("the preview is a pane in BOTH side (widescreen) and bottom (standard) — the 'same system' contract")
    func previewIsInThePaneSystemInBothModes() {
        // The CD's report: side preview has a pane head, bottom preview didn't, because
        // bottom preview bypassed the pane system. After F7 both place a .preview leaf in
        // the pane list, so both get the same head/clip from the one renderer.
        let side = PaneList.forLayout(
            mode: .widescreen, showsPreview: true, showsDocumentGrid: true,
            widescreen: WidescreenVisibility(library: true, preview: true, reading: false))
        let bottom = PaneList.forLayout(
            mode: .standard, showsPreview: true, showsDocumentGrid: true,
            widescreen: WidescreenVisibility(library: false, preview: false, reading: false))
        #expect(side.kinds.contains(.preview))
        #expect(bottom.kinds.contains(.preview))
    }

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
