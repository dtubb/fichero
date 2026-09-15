@testable import Fichero
import Foundation
import Testing

/// spec: panes-magnifiers-workspaces §"v2 workspace design" — the six default workspaces AS DATA.
/// These pin each composition (kinds, nesting, per-pane config) so a default is a data change and
/// a saved workspace is the same `PaneList` shape.
struct BuiltInWorkspaceLayoutTests {

    /// Every leaf (kind + config) anywhere in a list, splits flattened.
    private func allLeaves(_ list: PaneList) -> [(kind: PaneKind, config: PaneConfig)] {
        var out: [(kind: PaneKind, config: PaneConfig)] = []
        func walk(_ node: PaneNode) {
            switch node {
            case let .leaf(_, kind, _, config): out.append((kind: kind, config: config))
            case let .split(_, _, children): children.forEach(walk)
            }
        }
        list.nodes.forEach(walk)
        return out
    }

    @Test("the six defaults map to ⌘⌥1–6 in declaration order")
    func slotsAreOneThroughSix() {
        #expect(BuiltInWorkspaceLayout.allCases.count == 6)
        for (index, layout) in BuiltInWorkspaceLayout.allCases.enumerated() {
            #expect(layout.defaultSlot == index + 1)
        }
        #expect(BuiltInWorkspaceLayout.read.defaultSlot == 1)
    }

    @Test("Read is three columns — library, preview, reader")
    func readIsThreeColumns() {
        #expect(BuiltInWorkspaceLayout.read.panes.kinds == [.library, .preview, .reading])
        #expect(BuiltInWorkspaceLayout.read.panes.nodes.count == 3)
    }

    @Test("Browse nests a column-browser over a reader, beside the page")
    func browseNestsVertically() {
        let nodes = BuiltInWorkspaceLayout.browse.panes.nodes
        guard case let .split(_, axis, children) = nodes.first else {
            Issue.record("browse should open with a split"); return
        }
        #expect(axis == .vertical)
        #expect(children.count == 2)
        if case let .leaf(_, kind, _, config) = children.first {
            #expect(kind == .library)
            #expect(config.libraryLayout == "columns")
        } else {
            Issue.record("first child should be the library leaf")
        }
    }

    @Test("Transcribe shows a word-box preview beside the plain page")
    func transcribeHasWordBoxes() {
        let previews = allLeaves(BuiltInWorkspaceLayout.transcribe.panes).filter { $0.kind == .preview }
        #expect(previews.count == 2)
        #expect(previews.contains { $0.config.previewWordBoxes == true })
    }

    @Test("Compare is two symmetric witness columns — page over reader each")
    func compareIsTwoColumns() {
        let nodes = BuiltInWorkspaceLayout.compare.panes.nodes
        #expect(nodes.count == 2)
        for node in nodes {
            // Two panes per column (page over reader). The per-column library/related nav is
            // deferred until the library pane is instance-safe (panes.instance-safe).
            #expect(node.leafCount == 2)
            #expect(node.kinds == [.preview, .reading])
        }
    }

    @Test("no built-in mounts two library panes until the library pane is instance-safe")
    func noBuiltInHasTwoLibraryPanes() {
        // A guard test: two library content views in one window loop on shared window state
        // (spec panes.instance-safe, CD live 2026-09-15). Until that's fixed, no default may mount
        // more than one library pane. This catches the regression at the DATA level.
        for layout in BuiltInWorkspaceLayout.allCases {
            let libraryCount = allLeaves(layout.panes).filter { $0.kind == .library }.count
            #expect(libraryCount <= 1, "\(layout.title) mounts \(libraryCount) library panes")
        }
    }

    @Test("Catalogue and Claims dock an inspector; the others don't")
    func inspectorOnlyWhereIntended() {
        for layout in BuiltInWorkspaceLayout.allCases {
            let hasInspector = layout.panes.kinds.contains(.inspector)
            let shouldHave = layout == .catalogue || layout == .claims
            #expect(hasInspector == shouldHave, "\(layout.title) inspector presence")
        }
    }

    @Test("Claims points the library at claims content")
    func claimsBrowsesClaims() {
        let library = allLeaves(BuiltInWorkspaceLayout.claims.panes).first { $0.kind == .library }
        #expect(library?.config.libraryContentKind == "claims")
    }

    @Test("every default round-trips through JSON (a workspace is a PaneList)")
    func everyDefaultRoundTrips() throws {
        for layout in BuiltInWorkspaceLayout.allCases {
            // Capture ONE instance: `.panes` mints fresh pane ids on each access, so comparing a
            // decode against a second `.panes` call would differ only by UUID (the round-trip is fine).
            let panes = layout.panes
            let decoded = try JSONDecoder().decode(PaneList.self, from: JSONEncoder().encode(panes))
            #expect(decoded == panes, "\(layout.title) should round-trip")
        }
    }
}
