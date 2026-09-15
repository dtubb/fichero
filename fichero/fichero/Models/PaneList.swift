import Foundation

// MARK: - Pane-list model (F7)
//
// spec: docs/contributor_manual/specs/ui/panes-magnifiers-workspaces.md §F7.
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
    case leaf(id: UUID, kind: PaneKind, scope: PaneScope)
    case split(id: UUID, axis: SplitAxis, children: [PaneNode])

    var id: UUID {
        switch self {
        case let .leaf(id, _, _): return id
        case let .split(id, _, _): return id
        }
    }

    /// A fresh leaf pane of `kind`, following the current selection.
    static func leaf(_ kind: PaneKind, scope: PaneScope = .current) -> PaneNode {
        .leaf(id: UUID(), kind: kind, scope: scope)
    }

    /// A split of `children` along `axis`.
    static func split(_ axis: SplitAxis, _ children: [PaneNode]) -> PaneNode {
        .split(id: UUID(), axis: axis, children: children)
    }

    /// Every kind this node (recursively) contains.
    var kinds: Set<PaneKind> {
        switch self {
        case let .leaf(_, kind, _): return [kind]
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

    /// Whether any TOP-LEVEL leaf of `kind` exists (what a kind toggle acts on).
    func containsTopLevelLeaf(of kind: PaneKind) -> Bool {
        nodes.contains { if case let .leaf(_, leafKind, _) = $0 { return leafKind == kind }; return false }
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
                if case let .leaf(_, leafKind, _) = $0 { return leafKind != kind }
                return true
            }
            return PaneList(kept)
        }
        return PaneList(nodes + [.leaf(kind)])
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

    /// The pane composition for a legacy `LayoutMode`, as DATA — so every mode renders
    /// through the ONE pane renderer instead of `centerContentRouting`'s hand-branched
    /// `switch` (spec §F7 "one renderer", RATIFIED 2026-09-13/14). This reproduces that
    /// switch's structure exactly, so the migration is behavior-preserving:
    ///
    ///   - a non-library/search mode (`showsPreview == false`) owns the whole area → one
    ///     library(content) pane;
    ///   - `.none` → library alone (grid) or preview alone (grid hidden);
    ///   - `.standard` → library OVER preview, a VERTICAL split (the "bottom preview"); the
    ///     split node is what gives that preview the SAME pane head — breadcrumb, close,
    ///     clip — the widescreen side preview has and the legacy `PlatformVSplitView` lacked
    ///     ("not using the same system", CD 2026-09-14);
    ///   - `.widescreen` → the horizontal visibility list (library · preview · reading).
    ///
    /// Rendering rule the renderer honours: TOP-LEVEL nodes lay out horizontally (a row); a
    /// `.split` node arranges its children along its own axis. That one recursion subsumes
    /// both the old widescreen HStack and the old standard VSplit.
    static func forLayout(
        mode: LayoutMode,
        showsPreview: Bool,
        showsDocumentGrid: Bool,
        widescreen: WidescreenVisibility
    ) -> PaneList {
        guard showsPreview else { return PaneList([.leaf(.library)]) }
        switch mode {
        case .none:
            return PaneList([.leaf(showsDocumentGrid ? .library : .preview)])
        case .standard:
            guard showsDocumentGrid else { return PaneList([.leaf(.preview)]) }
            return PaneList([.split(.vertical, [.leaf(.library), .leaf(.preview)])])
        case .widescreen:
            return .fromVisibility(
                library: widescreen.library,
                preview: widescreen.preview,
                reading: widescreen.reading,
                chat: false
            )
        }
    }
}

/// The three widescreen pane-visibility flags, grouped so `PaneList.forLayout` reads as one
/// "widescreen inputs" argument (and stays within the tuple-size / parameter-count limits).
struct WidescreenVisibility: Sendable, Hashable {
    var library: Bool
    var preview: Bool
    var reading: Bool
}
