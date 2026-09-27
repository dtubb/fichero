import CryptoKit
import Foundation

//  Extracted for file_length (#5113). Byte-for-byte, behaviour unchanged. Imports are the
//  SOURCE file's, and the path was checked free before writing — both lessons from
//  earlier batches in this milestone.

struct PaneList: Codable, Sendable, Hashable {
    var nodes: [PaneNode]

    init(_ nodes: [PaneNode]) { self.nodes = nodes }

    /// Every kind anywhere in the list.
    var kinds: Set<PaneKind> {
        nodes.reduce(into: []) { $0.formUnion($1.kinds) }
    }

    /// Total rendered panes (leaves), splits flattened — 1 means a single pane fills the window.
    var leafCount: Int {
        nodes.reduce(0) { $0 + $1.leafCount }
    }

    /// Whether any TOP-LEVEL leaf of `kind` exists (what a kind toggle acts on).
    func containsTopLevelLeaf(of kind: PaneKind) -> Bool {
        nodes.contains { if case let .leaf(_, leafKind, _, _) = $0 { return leafKind == kind }; return false }
    }

    /// Toggle a top-level pane of `kind`: remove every top-level leaf of that kind
    /// if any exist, else append a fresh one (current scope). This is the toggle
    /// contract that makes the toolbar reliable — it ALWAYS changes the list, in
    /// every layout mode, because the list is the single source of truth (no
    /// per-mode Bool that a renderer might ignore). Splits are left untouched;
    /// toggling only adds/removes whole top-level panes.
    func toggling(_ kind: PaneKind) -> PaneList {
        if containsTopLevelLeaf(of: kind) {
            let kept = nodes.filter {
                if case let .leaf(_, leafKind, _, _) = $0 { return leafKind != kind }
                return true
            }
            return PaneList(kept)
        }
        return PaneList(nodes + [.leaf(kind)])
    }

    /// Remove the single pane with `id`, leaving every other pane and the split structure intact
    /// (spec panes.close.this-pane-only). The per-instance close: closing one pane never drops its
    /// siblings or collapses the row — a split that loses a child collapses to the survivor.
    func removingLeaf(_ id: UUID) -> PaneList {
        PaneList(nodes.compactMap { $0.removingLeaf(id) })
    }

    /// Split the single pane with `id` along `axis` — replace it with a split of [the pane, a fresh
    /// duplicate] — leaving every OTHER pane untouched (spec panes.split.focused-only). The
    /// per-instance split: splitting one pane never splits the others.
    func splittingLeaf(_ id: UUID, axis: SplitAxis) -> PaneList {
        PaneList(nodes.map { $0.splittingLeaf(id, axis: axis) })
    }

    /// Change the KIND of the single pane with `id` (spec panes.head.kind-switch) — turn a reader
    /// into a preview, a preview into a library, etc. Preserves id/scope/config; every other pane is
    /// untouched.
    func changingLeafKind(_ id: UUID, to kind: PaneKind) -> PaneList {
        PaneList(nodes.map { $0.changingKind(id, to: kind) })
    }

    /// Change the leaf `id`'s explicit CONTENT kind (#4884, spec panes.model.per-pane-scope-and-
    /// kind-unread) — Documents/Claims/Entities for a library pane. `nil` clears it (follow the
    /// window again). Every other pane is untouched.
    func changingLeafContentKind(_ id: UUID, to contentKind: String?) -> PaneList {
        PaneList(nodes.map { $0.changingContentKind(id, to: contentKind) })
    }

    /// Change the leaf `id`'s explicit LIBRARY LAYOUT (#4965, slice E) — the View menu's Icon/
    /// List/Table/… commands write here when a Library leaf is focused. `nil` clears it (follow
    /// the window/workspace default again). Every other pane is untouched — same shape as
    /// `changingLeafContentKind` above.
    func changingLeafLibraryLayout(_ id: UUID, to layout: String?) -> PaneList {
        PaneList(nodes.map { $0.changingLibraryLayout(id, to: layout) })
    }

    /// The `PaneConfig` of the leaf with `id`, nested splits included — `nil` if no leaf has that
    /// id. Slice E (#4965): the View menu reads a focused leaf's CURRENT `libraryLayout` through
    /// this, so its checkmark reflects the pane's own explicit choice, not the window default.
    func config(for id: UUID) -> PaneConfig? {
        var found: PaneConfig?
        func walk(_ node: PaneNode) {
            guard found == nil else { return }
            switch node {
            case let .leaf(leafId, _, _, config): if leafId == id { found = config }
            case let .split(_, _, children): children.forEach(walk)
            }
        }
        nodes.forEach(walk)
        return found
    }

    /// Every leaf id of `kind`, nested splits included (leading→trailing order).
    func leafIDs(of kind: PaneKind) -> [UUID] {
        var out: [UUID] = []
        func walk(_ node: PaneNode) {
            switch node {
            case let .leaf(id, leafKind, _, _): if leafKind == kind { out.append(id) }
            case let .split(_, _, children): children.forEach(walk)
            }
        }
        nodes.forEach(walk)
        return out
    }

    /// Show or hide a whole KIND — the directional twin of `toggling`, for the legacy show/hide
    /// toggles now that the applied `PaneList` is the source of truth (a toggle must still DO
    /// something once the Bool path is gone). Hiding removes every leaf of that kind, nested splits
    /// included, and is REFUSED if it would empty the window (the #1696 ≥1-pane invariant, re-homed
    /// onto the list); showing appends a fresh top-level leaf only if none of that kind exists.
    func settingVisible(_ kind: PaneKind, _ visible: Bool) -> PaneList {
        let ids = leafIDs(of: kind)
        if visible {
            return ids.isEmpty ? PaneList(nodes + [.leaf(kind)]) : self
        }
        guard !ids.isEmpty else { return self }
        var result = self
        for id in ids { result = result.removingLeaf(id) }
        return result.nodes.isEmpty ? self : result   // never empty the window
    }

    /// The leaf ids that must render as SECONDARY panes — every leaf whose kind already appeared
    /// earlier in traversal order. A window-scoped `focusedSceneValue` admits only ONE publisher
    /// per key; two same-kind panes each mount their own `SplittablePane` and both publish the
    /// SAME keys every frame → SwiftUI's "FocusedValue update tried to update multiple times per
    /// frame" fault → recursive scene invalidation (the applied-workspace render loop that
    /// beachballed Compare, CD live 2026-09-15; spec panes.instance-safe). Flagging every
    /// duplicate secondary routes it through the already-proven non-publishing branch
    /// (`\.isSecondarySplitPane`). Pure and total — this is the structural guard a unit test
    /// asserts, so a default that would loop fails at the MODEL level before it can beachball.
    func secondaryLeafIDs() -> Set<UUID> {
        var seenKinds: Set<PaneKind> = []
        var secondary: Set<UUID> = []
        func walk(_ node: PaneNode) {
            switch node {
            case let .leaf(id, kind, _, _):
                if seenKinds.contains(kind) { secondary.insert(id) } else { seenKinds.insert(kind) }
            case let .split(_, _, children):
                children.forEach(walk)
            }
        }
        nodes.forEach(walk)
        return secondary
    }

    // `fromVisibility` was DELETED (#4685 leftover cleanup, 2026-09-18): it derived a PaneList
    // from four Bool flags for the pre-workspace renderer (`widescreenPaneSpecs`, PaneSpec.swift),
    // which #4685 also deleted as callerless — this was its only production caller. The
    // reliability invariant it partly demonstrated ("flipping a flag always changes the visible
    // set") is independently pinned against the LIVE mechanism by
    // `PaneListTests.toggleAlwaysChangesKinds` (`.toggling(_:)`), so nothing was lost.
}
