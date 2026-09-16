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

    @Test("Read is the default: library over reader, beside the preview")
    func readIsLibraryOverReaderBesidePreview() {
        // CD 2026-09-16: 1 library above 1 reader (a vertical split), beside 1 preview.
        let nodes = BuiltInWorkspaceLayout.read.panes.nodes
        #expect(nodes.count == 2)
        guard case let .split(_, axis, children) = nodes.first else {
            Issue.record("Read should open with a vertical split (library over reader)"); return
        }
        #expect(axis == .vertical)
        #expect(children.map(\.kinds) == [[.library], [.reading]])
        // The preview is the second top-level column.
        #expect(nodes.last?.kinds == [.preview])
        #expect(BuiltInWorkspaceLayout.read.panes.kinds == [.library, .preview, .reading])
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
            // Two panes per column (page over reader). The per-column library/related NAV the CD
            // designed is deferred: TWO library panes loop (loadLibraryData / focused-value storm,
            // CD live 2026-09-15, ⌘⌥4 beachball) until the library pane is instance-safe. Two
            // previews + two readers is fine (Transcribe proves two previews).
            #expect(node.leafCount == 2)
            #expect(node.kinds == [.preview, .reading])
        }
    }

    @Test("no built-in mounts two library panes until the library pane is instance-safe")
    func noBuiltInMountsTwoLibraries() {
        // The library content view loops when mounted twice in one window (shared data/selection +
        // focused-value collision → the ⌘⌥4 beachball). Until that's fixed at the source, a DATA
        // guard keeps every default to at most one library pane — the reliability line.
        for layout in BuiltInWorkspaceLayout.allCases {
            let libraryCount = allLeaves(layout.panes).filter { $0.kind == .library }.count
            #expect(libraryCount <= 1, "\(layout.title) mounts \(libraryCount) library panes — it will loop")
        }
    }

    /// Every leaf's (id, kind), splits flattened — for the instance-safety guard, which reasons
    /// about which panes publish window-scoped focus keys.
    private func allLeafIDs(_ list: PaneList) -> [(id: UUID, kind: PaneKind)] {
        var out: [(id: UUID, kind: PaneKind)] = []
        func walk(_ node: PaneNode) {
            switch node {
            case let .leaf(id, kind, _, _): out.append((id: id, kind: kind))
            case let .split(_, _, children): children.forEach(walk)
            }
        }
        list.nodes.forEach(walk)
        return out
    }

    @Test("every built-in is instance-safe: at most one PRIMARY pane per kind")
    func everyBuiltInIsInstanceSafe() {
        // The structural guard that replaces "no two libraries" (spec panes.instance-safe): a
        // window-scoped focused value admits ONE publisher per key, so a workspace with two
        // same-kind panes must flag every duplicate secondary (PaneList.secondaryLeafIDs →
        // \.isSecondarySplitPane). This asserts the model half directly: among the leaves that
        // are NOT flagged secondary (the primaries — the publishers), each kind appears at most
        // once. If it doesn't, that layout WILL loop the scene graph. Deterministic, pure, and
        // canvas-bug-immune (a Scene-less ImageRenderer can't reproduce the focused-value fault).
        for layout in BuiltInWorkspaceLayout.allCases {
            let panes = layout.panes
            let secondary = panes.secondaryLeafIDs()
            let primaries = allLeafIDs(panes).filter { !secondary.contains($0.id) }
            var perKind: [PaneKind: Int] = [:]
            for pane in primaries { perKind[pane.kind, default: 0] += 1 }
            for (kind, count) in perKind {
                #expect(count == 1, "\(layout.title) has \(count) primary \(kind) panes — it will loop")
            }
        }
    }

    @Test("Compare flags one duplicate of each kind secondary (preview, reader)")
    func compareFlagsDuplicatesSecondary() {
        // The two-witness Compare mounts two each of preview / reader; exactly the SECOND of each
        // must be secondary so only one publishes per window-scoped key (the focused-value fix).
        let panes = BuiltInWorkspaceLayout.compare.panes
        #expect(panes.secondaryLeafIDs().count == 2)
        let secondaryKinds = allLeafIDs(panes)
            .filter { panes.secondaryLeafIDs().contains($0.id) }
            .map(\.kind)
        #expect(Set(secondaryKinds) == [.preview, .reading])
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
