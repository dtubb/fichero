import CryptoKit
import Foundation

// MARK: - Deterministic ids (SF6 review finding — built-in workspace stability)

extension UUID {
    /// A UUID derived deterministically from `name`: the SAME `name` always produces the SAME
    /// UUID (this process, the next launch, forever), unlike the random `UUID()` initializer.
    /// RFC 4122 name-based hashing (the same idea as a v3/v5 namespace UUID), MD5-based — MD5 is
    /// fine here, this is an IDENTITY key, not a security boundary. Used to give built-in
    /// workspace panes a stable identity (`PaneNode.stableLeaf`/`.stableSplit`) instead of a fresh
    /// random one on every access.
    init(stableName name: String) {
        let digest = Insecure.MD5.hash(data: Data(name.utf8))
        var bytes = Array(digest)
        bytes[6] = (bytes[6] & 0x0F) | 0x30 // version 3 (name-based, MD5) — cosmetic, not load-bearing
        bytes[8] = (bytes[8] & 0x3F) | 0x80 // RFC 4122 variant — likewise cosmetic
        self = NSUUID(uuidBytes: bytes) as UUID
    }
}

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
    /// A HARD pin — wins over `paneFraction` on the same leaf, and (in `WorkspaceSplitStack`)
    /// ignores any stored drag state (#4688).
    ///
    /// #4848: for a `.library` leaf, this names the VISIBLE ICON STRIP height only — NOT the
    /// whole pane's extent. `PaneSpec.childExtents` widens it by the pane's own chrome (its head
    /// bar + bottom mini-toolbar, via `PaneSpec.libraryStripExtent`) before handing it to
    /// `WorkspaceSplitStack`, so the strip's 72pt is headroom for icons, not for icons AND chrome
    /// squeezed into the same 72pt (the bug: no icons showed at all, because the chrome alone
    /// used about that much).
    var paneExtent: Double?
    /// Preferred PROPORTIONAL extent — a share (0–1) of the parent split's own extent — for a
    /// content pane that should hold its proportion across a 13" laptop and a 32" display instead
    /// of a flat point value (#4688, CD 2026-09-17: "think through % ... for the various default
    /// workspaces"). Seeds a resizable column in `WorkspaceSplitStack`; a drag persists over it the
    /// same way an absolute default used to. Ignored when `paneExtent` is also set.
    var paneFraction: Double?

    init(
        libraryContentKind: String? = nil,
        libraryLayout: String? = nil,
        previewLens: String? = nil,
        previewWordBoxes: Bool? = nil,
        paneExtent: Double? = nil,
        paneFraction: Double? = nil
    ) {
        self.libraryContentKind = libraryContentKind
        self.libraryLayout = libraryLayout
        self.previewLens = previewLens
        self.previewWordBoxes = previewWordBoxes
        self.paneExtent = paneExtent
        self.paneFraction = paneFraction
    }

    /// Follow the window default on every axis (an unconfigured pane).
    static let none = PaneConfig()

    /// Whether this pane overrides any presentation default.
    var isConfigured: Bool {
        libraryContentKind != nil || libraryLayout != nil || previewLens != nil
            || previewWordBoxes != nil || paneExtent != nil || paneFraction != nil
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

    /// A leaf whose id is DETERMINISTIC, derived from `name` (SF6 review finding) — for BUILT-IN
    /// workspace definitions ONLY. `BuiltInWorkspaceLayout.panes` used the plain `.leaf(_:)` above,
    /// which mints a FRESH random id on every single access; `WorkspaceSplitStack`/`PaneSpec` key
    /// their per-instance storage (a dragged divider's width, a pane's own split state) off a
    /// leaf's id, so re-deriving the SAME built-in composition (navigating Read → Browse → Read,
    /// or simply relaunching) silently lost every drag and orphaned two `@SceneStorage` keys per
    /// apply. Give `name` a value unique within one `BuiltInWorkspaceLayout` case (e.g.
    /// `"\(rawValue).library"`) — the SAME name always yields the SAME id, in this process or the
    /// next; a DIFFERENT name (a different pane, a different built-in) yields a different one.
    /// Runtime mutations (`toggling`, `splittingLeaf`'s duplicate, `settingVisible`'s appended
    /// leaf) must keep using the plain `.leaf(_:)` above — a stable id there would make two
    /// toggled-on panes of the same kind collide instead of coexisting.
    static func stableLeaf(
        _ kind: PaneKind, named name: String, scope: PaneScope = .current, config: PaneConfig = .none
    ) -> PaneNode {
        .leaf(id: UUID(stableName: name), kind: kind, scope: scope, config: config)
    }

    /// The `stableLeaf` twin for a split node — see `stableLeaf` for why and when.
    static func stableSplit(_ axis: SplitAxis, named name: String, _ children: [PaneNode]) -> PaneNode {
        .split(id: UUID(stableName: name), axis: axis, children: children)
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

    /// This node with the leaf `id`'s `config.libraryContentKind` changed to `newContentKind`,
    /// preserving everything else (#4884: the pane-head content-kind chip — Documents/Claims/
    /// Entities — writes here, not `LibraryView`'s local `@State`, so the choice is a real,
    /// SAVED per-pane setting rather than a session-only picker). `nil` clears the pane's
    /// explicit choice (goes back to following the window). Every other pane is untouched — the
    /// same "one leaf only" contract `changingKind` above already gives pane-KIND switches.
    func changingContentKind(_ target: UUID, to newContentKind: String?) -> PaneNode {
        switch self {
        case let .leaf(id, kind, scope, config):
            guard id == target else { return self }
            var updated = config
            updated.libraryContentKind = newContentKind
            return .leaf(id: id, kind: kind, scope: scope, config: updated)
        case let .split(id, axis, children):
            return .split(id: id, axis: axis, children: children.map { $0.changingContentKind(target, to: newContentKind) })
        }
    }

    /// This node with the leaf `id`'s `config.libraryLayout` changed to `newLayout`, preserving
    /// everything else — the LAYOUT sibling of `changingContentKind` above (#4965, source-model
    /// panes recon slice E, 2026-09-20: the View menu's Icon/List/Table commands write HERE, to
    /// the focused pane's own field, not a window-wide setting). Exact same shape as
    /// `changingContentKind`: `nil` clears the pane's explicit choice (back to following the
    /// window/workspace default); every other pane is untouched.
    func changingLibraryLayout(_ target: UUID, to newLayout: String?) -> PaneNode {
        switch self {
        case let .leaf(id, kind, scope, config):
            guard id == target else { return self }
            var updated = config
            updated.libraryLayout = newLayout
            return .leaf(id: id, kind: kind, scope: scope, config: updated)
        case let .split(id, axis, children):
            return .split(id: id, axis: axis, children: children.map { $0.changingLibraryLayout(target, to: newLayout) })
        }
    }
}

/// A window's centre composition: an ordered list of top-level pane nodes
/// (the "columns"), each of which may itself be split. Codable → a saved workspace
/// is exactly a `PaneList`.
