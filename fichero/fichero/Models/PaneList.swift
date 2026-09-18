import Foundation

// MARK: - Pane-list model (F7)
//
// spec: docs/contributor_manual/specs/ui/panes-workspaces.md §F7.
//
// The reliable, composable replacement for `WidescreenPanePlan`'s four `showsXPane`
// Bools. A window's centre is an ORDERED LIST of panes; each pane carries a KIND
// and a SCOPE (which library / document / folder it shows), and can be split
// (asymmetrically, by nesting). This is the single source of truth for composition:
//   - toggles mutate the list (so a toggle always does something, in every mode);
//   - two entries of the same kind with different scopes give "different previews /
//     different libraries side by side";
//   - nested splits give "2 over 1" instead of a symmetric 2×2.
//
// This file is the PURE model only — Codable, value-typed, no SwiftUI. Nothing wires
// it into the renderer yet (that is the next F7 step, done with the design lead); it
// exists so the composition logic can be unit-tested off-view first.

/// What a pane shows. (Mirrors the current `PaneSpec.Kind`; kept as its own pure
/// type so the model has no view dependency.)
enum PaneKind: String, Codable, CaseIterable, Sendable, Hashable {
    case library
    case preview
    case reading
    case inspector
    case chat
}

/// What a pane is scoped to. All fields optional: a `nil` field means "follow the
/// window's current selection" for that dimension. A non-nil `libraryId` is what
/// lets one pane show a DIFFERENT library than another in the same window.
struct PaneScope: Codable, Sendable, Hashable {
    var libraryId: String?
    var documentId: String?
    var folderId: String?

    init(libraryId: String? = nil, documentId: String? = nil, folderId: String? = nil) {
        self.libraryId = libraryId
        self.documentId = documentId
        self.folderId = folderId
    }

    /// Follow the window's current selection on every dimension.
    static let current = PaneScope()

    /// Whether this scope pins any dimension (vs. following the current selection).
    var isPinned: Bool { libraryId != nil || documentId != nil || folderId != nil }
}

/// Per-pane PRESENTATION — the difference between "library" and "library showing claims as a
/// table", or "preview" and "preview with word boxes". This is what turns a workspace from a
/// show/hide preset into a real composition (spec §"v2 workspace design"). Stored as stable raw
/// strings (not the app enums) so the pure model stays decoupled and a saved workspace's JSON
/// survives an enum rename — the same lenient-string discipline `WindowLayoutSnapshot` uses; the
/// renderer maps them to `LibraryContentKind` / `LibraryLayout` / `PreviewLens` with a fallback.
/// All-nil = "follow the window default", so an unconfigured pane behaves exactly as before.
struct PaneConfig: Codable, Sendable, Hashable {
    /// Library pane — what it browses: "documents" | "entities" | "claims" (`LibraryContentKind`).
    var libraryContentKind: String?
    /// Library pane — how it lays out: a `LibraryLayout` rawValue ("icons"/"list"/"table"/…).
    var libraryLayout: String?
    /// Preview pane — "preview" | "edit" (`PreviewLens`).
    var previewLens: String?
    /// Preview pane — draw the OCR word-box overlay (today a global `imagePreview.inlineTextEnabled`).
    var previewWordBoxes: Bool?
    /// Preferred FIXED extent (pt) along the parent split's axis — width in a horizontal split,
    /// height in a vertical one. Set on a film-strip pane (the narrow library-icons strip at the
    /// bottom of Transcribe/Compare, ~72pt) so it stays narrow while the content flexes (CD
    /// 2026-09-16). `nil` = follow the normal sizing (resizable column, or flex if it's the tail).
    var paneExtent: Double?

    init(
        libraryContentKind: String? = nil,
        libraryLayout: String? = nil,
        previewLens: String? = nil,
        previewWordBoxes: Bool? = nil,
        paneExtent: Double? = nil
    ) {
        self.libraryContentKind = libraryContentKind
        self.libraryLayout = libraryLayout
        self.previewLens = previewLens
        self.previewWordBoxes = previewWordBoxes
        self.paneExtent = paneExtent
    }

    /// Follow the window default on every axis (an unconfigured pane).
    static let none = PaneConfig()

    /// Whether this pane overrides any presentation default.
    var isConfigured: Bool {
        libraryContentKind != nil || libraryLayout != nil || previewLens != nil
            || previewWordBoxes != nil || paneExtent != nil
    }
}

/// The split axis of a pane's sub-panes.
enum SplitAxis: String, Codable, Sendable, Hashable {
    case horizontal
    case vertical
}

/// A node in a window's pane composition: either a LEAF (one kind+scope) or a
/// SPLIT of child nodes along an axis. `indirect` because a split holds nodes.
/// Nesting is what expresses ASYMMETRIC layouts, e.g. "2 over 1":
///   .split(.vertical, [.split(.horizontal, [a, b]), c])
indirect enum PaneNode: Codable, Sendable, Hashable, Identifiable {
    case leaf(id: UUID, kind: PaneKind, scope: PaneScope, config: PaneConfig)
    case split(id: UUID, axis: SplitAxis, children: [PaneNode])

    var id: UUID {
        switch self {
        case let .leaf(id, _, _, _): return id
        case let .split(id, _, _): return id
        }
    }

    /// A fresh leaf pane of `kind`, following the current selection, with no presentation
    /// override (`config` all-nil) unless one is given.
    static func leaf(_ kind: PaneKind, scope: PaneScope = .current, config: PaneConfig = .none) -> PaneNode {
        .leaf(id: UUID(), kind: kind, scope: scope, config: config)
    }

    /// A split of `children` along `axis`.
    static func split(_ axis: SplitAxis, _ children: [PaneNode]) -> PaneNode {
        .split(id: UUID(), axis: axis, children: children)
    }

    /// Every kind this node (recursively) contains.
    var kinds: Set<PaneKind> {
        switch self {
        case let .leaf(_, kind, _, _): return [kind]
        case let .split(_, _, children): return children.reduce(into: []) { $0.formUnion($1.kinds) }
        }
    }

    /// The leaf count (how many rendered panes this node flattens to).
    var leafCount: Int {
        switch self {
        case .leaf: return 1
        case let .split(_, _, children): return children.reduce(0) { $0 + $1.leafCount }
        }
    }

    /// This node with the leaf `id` removed, or nil if it empties (spec panes.close.this-pane-only).
    /// A split left with ONE child collapses to that child (no orphan split); one that empties
    /// returns nil. Every OTHER pane keeps its identity — the fix for "closing a pane closes the
    /// whole row": removing one leaf leaves its siblings untouched.
    func removingLeaf(_ target: UUID) -> PaneNode? {
        switch self {
        case let .leaf(id, _, _, _):
            return id == target ? nil : self
        case let .split(id, axis, children):
            let kept = children.compactMap { $0.removingLeaf(target) }
            if kept.isEmpty { return nil }
            if kept.count == 1 { return kept[0] }
            return .split(id: id, axis: axis, children: kept)
        }
    }

    /// This node with the leaf `id` replaced by a split of [that leaf, a fresh duplicate] along
    /// `axis` (spec panes.split.focused-only). Every OTHER pane is untouched — the fix for
    /// "splitting one pane splits them all". A no-op if `id` isn't a leaf in this node.
    func splittingLeaf(_ target: UUID, axis: SplitAxis) -> PaneNode {
        switch self {
        case let .leaf(id, kind, scope, config):
            guard id == target else { return self }
            return .split(axis, [
                .leaf(id: id, kind: kind, scope: scope, config: config),
                .leaf(kind, scope: scope, config: config)  // the duplicate gets a fresh id
            ])
        case let .split(id, axis: splitAxis, children):
            return .split(id: id, axis: splitAxis, children: children.map { $0.splittingLeaf(target, axis: axis) })
        }
    }

    /// This node with the leaf `id`'s KIND changed to `newKind`, preserving its id, scope and config
    /// (spec panes.head.kind-switch — the head's far-left kind menu). Every other pane is untouched.
    func changingKind(_ target: UUID, to newKind: PaneKind) -> PaneNode {
        switch self {
        case let .leaf(id, _, scope, config):
            return id == target ? .leaf(id: id, kind: newKind, scope: scope, config: config) : self
        case let .split(id, axis, children):
            return .split(id: id, axis: axis, children: children.map { $0.changingKind(target, to: newKind) })
        }
    }
}

/// A window's centre composition: an ordered list of top-level pane nodes
/// (the "columns"), each of which may itself be split. Codable → a saved workspace
/// is exactly a `PaneList`.
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

    /// The visible top-level panes derived from the window's visibility flags, in
    /// leading→trailing order (library · preview · reading · chat). This is the ONE
    /// derivation every layout mode uses — so a flag (a toggle) controls its pane
    /// in EVERY mode, not only widescreen (spec §F7, the inert-toggle fix; today
    /// `.standard`/`.none` read only the library flag). Mode-independent BY
    /// CONSTRUCTION: "modes" differ only in their default flags and width/collapse
    /// behaviour, never in WHICH flags they honour. Each leaf follows the current
    /// selection (`.current`); scope-pinning is a later composition on top.
    static func fromVisibility(library: Bool, preview: Bool, reading: Bool, chat: Bool) -> PaneList {
        var nodes: [PaneNode] = []
        if library { nodes.append(.leaf(.library)) }
        if preview { nodes.append(.leaf(.preview)) }
        if reading { nodes.append(.leaf(.reading)) }
        if chat { nodes.append(.leaf(.chat)) }
        return PaneList(nodes)
    }
}
