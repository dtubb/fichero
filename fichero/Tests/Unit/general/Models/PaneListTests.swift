@testable import Fichero
import Foundation
import Testing

/// spec: panes-magnifiers-workspaces §F7 — the pure pane-list model that replaces
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

    // MARK: - scope (different libraries / previews side by side)

    @Test("two preview leaves with different scopes coexist")
    func sameKindDifferentScopesCoexist() {
        let a = PaneScope(libraryId: "lib-A")
        let b = PaneScope(libraryId: "lib-B")
        let list = PaneList([.leaf(.preview, scope: a), .leaf(.preview, scope: b)])
        // Two of a kind is representable — impossible in the four-Bool model.
        #expect(list.nodes.count == 2)
        #expect(list.kinds == [.preview])
        #expect(a != b)
        #expect(a.isPinned && b.isPinned)
        #expect(PaneScope.current.isPinned == false)
    }

    // MARK: - asymmetric split (2 over 1)

    @Test("an asymmetric 2-over-1 nesting flattens to three leaves")
    func asymmetricSplitLeafCount() {
        // 2 over 1: a vertical split of [ a horizontal split of [a, b], c ].
        let node = PaneNode.split(.vertical, [
            .split(.horizontal, [.leaf(.preview), .leaf(.preview)]),
            .leaf(.reading),
        ])
        #expect(node.leafCount == 3)
        #expect(node.kinds == [.preview, .reading])
    }

    // MARK: - Codable (a saved workspace IS a PaneList)

    @Test("a pane list round-trips through JSON identically (workspace persistence)")
    func codableRoundTrip() throws {
        let list = PaneList([
            .leaf(.library, scope: PaneScope(libraryId: "L", folderId: "F")),
            .split(.horizontal, [.leaf(.preview), .leaf(.reading)]),
        ])
        let data = try JSONEncoder().encode(list)
        let decoded = try JSONDecoder().decode(PaneList.self, from: data)
        #expect(decoded == list)
    }
}
