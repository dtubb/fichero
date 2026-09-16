@testable import Fichero
import Foundation
import Testing

/// spec: panes-magnifiers-workspaces §panes.close.this-pane-only + §panes.split.focused-only
/// (CD live 2026-09-15/16): "closing one pane closes BOTH" and "splitting one pane splits BOTH."
/// The root cause of both is a pane target keyed per-KIND instead of per-INSTANCE, so one verb hits
/// every same-kind pane. This suite pins the MODEL guarantee that a close/split targets EXACTLY ONE
/// pane: every leaf carries a unique identity, `removingLeaf`/`splittingLeaf` touch only that leaf,
/// and the applied-workspace storage keys (which scope split @SceneStorage + close routing) are
/// unique per pane position — the structural proxy for "close/split this pane only."
struct PaneInstanceIndependenceTests {

    /// Every leaf (id, kind), splits flattened, in traversal order.
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

    /// The built-ins that actually compose 2+ panes — the only ones where "close/split both" can bite.
    private var multiPaneBuiltIns: [BuiltInWorkspaceLayout] {
        BuiltInWorkspaceLayout.allCases.filter { allLeafIDs($0.panes).count >= 2 }
    }

    // MARK: - Identity: each pane is its own instance

    @Test("every leaf in every built-in has a unique id (no shared per-kind identity)")
    func everyLeafHasAUniqueID() {
        for layout in BuiltInWorkspaceLayout.allCases {
            let ids = allLeafIDs(layout.panes).map(\.id)
            #expect(
                Set(ids).count == ids.count,
                "\(layout.title) has \(ids.count) leaves but \(Set(ids).count) distinct ids — panes share identity, so one close/split would target all of them."
            )
        }
    }

    // MARK: - Close targets exactly one pane (spec panes.close.this-pane-only)

    @Test("removingLeaf removes exactly the targeted pane and leaves every sibling intact")
    func removingLeafTargetsExactlyOnePane() {
        for layout in multiPaneBuiltIns {
            let panes = layout.panes
            let leaves = allLeafIDs(panes)
            for target in leaves {
                let after = allLeafIDs(panes.removingLeaf(target.id))
                #expect(
                    after.count == leaves.count - 1,
                    "\(layout.title): closing one pane changed the count by \(leaves.count - after.count), not 1 — it closed more than the target."
                )
                #expect(
                    !after.contains { $0.id == target.id },
                    "\(layout.title): the targeted pane survived removingLeaf."
                )
                let survivingIDs = Set(after.map(\.id))
                for sibling in leaves where sibling.id != target.id {
                    #expect(
                        survivingIDs.contains(sibling.id),
                        "\(layout.title): closing the \(target.kind) pane also dropped a \(sibling.kind) sibling — the 'close both' bug."
                    )
                }
            }
        }
    }

    // MARK: - Split targets exactly one pane (spec panes.split.focused-only)

    @Test("splittingLeaf splits exactly the targeted pane and leaves every sibling untouched")
    func splittingLeafTargetsExactlyOnePane() {
        for layout in multiPaneBuiltIns {
            let panes = layout.panes
            let leaves = allLeafIDs(panes)
            for target in leaves {
                let after = allLeafIDs(panes.splittingLeaf(target.id, axis: .horizontal))
                // A split replaces the target leaf with [target, one fresh duplicate] → +1 leaf.
                #expect(
                    after.count == leaves.count + 1,
                    "\(layout.title): splitting one pane changed the count by \(after.count - leaves.count), not 1 — it split more than the target."
                )
                // Every ORIGINAL leaf id survives (the target keeps its identity; siblings untouched).
                let afterIDs = Set(after.map(\.id))
                for original in leaves {
                    #expect(
                        afterIDs.contains(original.id),
                        "\(layout.title): splitting the \(target.kind) pane disturbed the \(original.kind) pane's identity — the 'split both' bug."
                    )
                }
                // Exactly one NEW id was introduced (the duplicate), and it duplicates the target kind.
                let newIDs = afterIDs.subtracting(leaves.map(\.id))
                #expect(newIDs.count == 1, "\(layout.title): a split must add exactly one new pane.")
                let newKinds = after.filter { newIDs.contains($0.id) }.map(\.kind)
                #expect(newKinds == [target.kind], "\(layout.title): the split's duplicate must match the pane kind.")
            }
        }
    }

    // MARK: - Applied-path storage keys are unique per pane position

    /// Mirror of the applied-workspace key derivation in `ContentView.paneListRow` /
    /// `paneNodeView` / `paneSplitView` (PaneSpec.swift): the root split stack is keyed "root", a
    /// node at index path `keyPath` uses that path as its split @SceneStorage key, and each leaf's
    /// SplittablePane is keyed "pane-<keyPath>-<kind>". These keys are what scope the split state and
    /// the split/close routing to ONE pane; if two panes shared a key, splitting/closing one would
    /// hit both. This recomputes them from the model and asserts they are all distinct.
    private func appliedStorageKeys(_ list: PaneList) -> (splitKeys: [String], leafKeys: [String]) {
        var splitKeys: [String] = ["root"]  // paneListRow's top-level WorkspaceSplitStack
        var leafKeys: [String] = []
        func walk(_ node: PaneNode, keyPath: String) {
            switch node {
            case let .leaf(_, kind, _, _):
                // paneNodeView: slotId "pane-<keyPath>-<kind>" → kindContent splitKey "<slotId>-<kind>".
                leafKeys.append("pane-\(keyPath)-\(kind.rawValue)")
            case let .split(_, _, children):
                splitKeys.append(keyPath)  // paneSplitView's WorkspaceSplitStack storageKey
                for (idx, child) in children.enumerated() {
                    walk(child, keyPath: "\(keyPath).\(idx)")
                }
            }
        }
        for (index, node) in list.nodes.enumerated() {
            walk(node, keyPath: "\(index)")
        }
        return (splitKeys, leafKeys)
    }

    @Test("every applied-workspace pane gets a position-unique split/close storage key")
    func appliedStorageKeysAreUniquePerPane() {
        for layout in BuiltInWorkspaceLayout.allCases {
            let keys = appliedStorageKeys(layout.panes)
            #expect(
                Set(keys.leafKeys).count == keys.leafKeys.count,
                "\(layout.title): two panes derive the SAME SplittablePane storage key \(keys.leafKeys) — splitting/closing one would hit both (per-kind key, the bug)."
            )
            #expect(
                Set(keys.splitKeys).count == keys.splitKeys.count,
                "\(layout.title): two splits derive the same WorkspaceSplitStack key \(keys.splitKeys)."
            )
        }
    }
}
