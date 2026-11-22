@testable import Fichero
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/panes-workspaces.md -- `panes.head.one-menu-button` (#6741). The pane menu's
/// Split Right ▸ and Split Below ▸ list the kinds, so splitting adds THAT pane beside or below in one step. What breaks
/// without these: the split always duplicates the pane and the kind must be changed afterwards.
@MainActor
struct PaneSplitAddsKindTests {
    @Test("splitting a leaf adding a kind puts a fresh pane of that kind beside it; the rest is untouched")
    func splitAddsTheChosenKind() {
        let reader = UUID(), items = UUID()
        let list = PaneList([
            .leaf(id: items, kind: .library, scope: .current, config: .none),
            .leaf(id: reader, kind: .reading, scope: .current, config: PaneConfig(libraryContentKind: "claims"))
        ])
        let after = list.splittingLeaf(reader, axis: .vertical, adding: .preview)
        #expect(after.nodes[0].id == items)
        guard case let .split(_, axis, children) = after.nodes[1],
              case let .leaf(firstId, firstKind, _, _) = children[0],
              case let .leaf(newId, newKind, _, newConfig) = children[1] else {
            Issue.record("the reader should now be a split of two leaves"); return
        }
        #expect(axis == .vertical)
        #expect(firstId == reader && firstKind == .reading)
        #expect(newId != reader && newKind == .preview)
        #expect(newConfig.libraryContentKind == nil, "a pane of another kind does not inherit the reader's config")
    }

    @Test("adding the pane's own kind duplicates it, as the split did before")
    func sameKindDuplicates() {
        let lib = UUID()
        let config = PaneConfig(libraryContentKind: "claims")
        let list = PaneList([.leaf(id: lib, kind: .library, scope: .current, config: config)])
        let after = list.splittingLeaf(lib, axis: .horizontal, adding: .library)
        guard case let .split(_, _, children) = after.nodes[0],
              case let .leaf(_, kind, _, copied) = children[1] else {
            Issue.record("expected a split"); return
        }
        #expect(kind == .library)
        #expect(copied.libraryContentKind == "claims")
    }

    @Test("Split Right ▸ a kind splits side by side, Split Below ▸ stacks, each carrying the kind")
    func hookCarriesTheKind() {
        var captured: (SplitAxis, PaneSpec.Kind?)?
        let actions = PaneModelSplitHook(split: { captured = ($0, $1) }).splitAxisActions()
        actions.onSplitRight(.library)
        #expect(captured?.0 == .horizontal && captured?.1 == .library)
        actions.onSplitBelow(.reading)
        #expect(captured?.0 == .vertical && captured?.1 == .reading)
    }
}
