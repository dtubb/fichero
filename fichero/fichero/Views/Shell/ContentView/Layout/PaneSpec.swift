import SwiftUI

// MARK: - Chat mount decision (spec panes.chat.below-sidebar)

/// Pure decision for WHICH conversation the chat surface shows — extracted so
/// it is unit-testable without a running view. The chat surface (now beneath the
/// sidebar, `ContentView.chatSurface`) follows the view mode: a selected chat
/// names its conversation, anything else is a fresh one.
enum ChatMount {
    static func conversation(for viewMode: AppViewMode) -> Conversation? {
        if case .chat(let conversation) = viewMode { return conversation }
        return nil
    }
}

// MARK: - Pane system, step 1 (#13 / pane-system-proposal-2026-08-11)

/// One pane of the widescreen centre row.
///
/// Step 1 of the pane-system migration: the row is rendered from a LIST of
/// these instead of the hand-branched HStack in `centerContentRouting` —
/// behavior-identical (the list is still derived from `WidescreenPanePlan`,
/// not yet persisted or reorderable), but the shape is the one chat and the
/// terminal drawer extend by ADDING SPECS, and every pane is erased at its
/// own boundary, which is what caps the composed-generic crash class
/// (#4331: four incidents on 2026-08-11 alone, all rooted in this routing's
/// branch product type).
struct PaneSpec: Identifiable, Equatable {
    enum Kind: String, CaseIterable {
        case library
        case preview
        case reading
        case inspector
        case chat
        /// The Segments pane (#4942, approved 2026-09-27).
        case segments

        var title: String {
            switch self {
            case .library: "Library"
            case .preview: "Preview"
            case .reading: "Reader"
            case .inspector: "Inspector"
            case .chat: "Chat"
            case .segments: "Segments"
            }
        }

        var icon: String {
            switch self {
            case .library: "books.vertical"
            case .preview: "photo"
            case .reading: "book"
            case .inspector: "sidebar.trailing"
            case .chat: "bubble.left.and.bubble.right"
            case .segments: "list.bullet.rectangle"
            }
        }

        /// The kinds a pane can actually be switched TO. `.inspector` and
        /// `.chat` stay in `Kind`/`allCases` so the switcher's model type is
        /// total (`PaneKindSwitcher`, `kindContent(kind:...)`), but both are
        /// placeholder leaves today (`kindContent`'s `.inspector`/`.chat`
        /// arms render `PaneEmptyStateView`, not real content) — offering
        /// them in the kind-switch menu would let a click "switch" a pane to
        /// a dead end. Ship them here only when #4705 increments 6 (chat as
        /// a movable pane) / 7 (inspector as a real leaf) give them content.
        static var selectableKinds: [Kind] {
            allCases.filter { $0 != .inspector && $0 != .chat }
        }
    }

    let kind: Kind
    /// Fixed width when a divider governs this pane; nil = flexible.
    var fixedWidth: CGFloat?
    /// The pane's POSITION in the row. This is what makes the slot id — and therefore the split
    /// @SceneStorage and the split-command routing key — per-INSTANCE instead of per-KIND. Before
    /// this, `id == kind.rawValue`, so two panes of the same kind shared one split cell and one
    /// broadcast match: splitting/closing one hit them all (spec CD 2026-09-15,
    /// panes.split.focused-only). Position-scoping isolates each pane.
    var slot: Int = 0

    var id: String { "\(slot)-\(kind.rawValue)" }
}

/// Injected per pane SLOT so the head's kind icon can switch what the slot
/// hosts (Daniel, 2026-08-23: "clicking on the view type icon should let us
/// change what it is"). nil = the pane is not hosted in a switchable slot.
///
/// EQUATABLE BY SLOT ID (2026-08-24, the morning slowness): a bare closure
/// in the environment is never equal to itself, so every parent render read
/// as an environment CHANGE and re-walked the whole pane subtree — the
/// EnvironmentBox/copyItems stall storm in the live log. The closure
/// captures only the slot id, so identity by id is exact.
struct PaneKindSwitcher: Equatable {
    let slotId: String
    let switchKind: @MainActor (PaneSpec.Kind) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool { lhs.slotId == rhs.slotId }
}

private struct PaneKindSwitcherKey: EnvironmentKey {
    static let defaultValue: PaneKindSwitcher? = nil
}

extension EnvironmentValues {
    var paneKindSwitcher: PaneKindSwitcher? {
        get { self[PaneKindSwitcherKey.self] }
        set { self[PaneKindSwitcherKey.self] = newValue }
    }
}

/// Injected per pane SLOT (library leaves only) so the pane-head content-kind
/// chip (Documents/Claims/Entities) can set an EXPLICIT, SAVED kind for THIS
/// pane (#4884) — `PaneList.changingLeafContentKind`, not `LibraryView`'s
/// local `@State`. nil = this Library pane is not hosted in a switchable slot
/// (the compact iPhone reader stack's leaf, which sits outside the pane tree
/// entirely — `LibraryView.libraryContentKind` is that leaf's own fallback).
///
/// EQUATABLE BY SLOT ID ONLY — same reason as `PaneKindSwitcher` above (a bare
/// closure is never `==` itself, which re-walks the whole pane subtree on
/// every parent render).
struct PaneContentKindSwitcher: Equatable {
    let slotId: String
    let switchContentKind: @MainActor (LibraryContentKind?) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool { lhs.slotId == rhs.slotId }
}

private struct PaneContentKindSwitcherKey: EnvironmentKey {
    static let defaultValue: PaneContentKindSwitcher? = nil
}

private struct PaneContentKindKey: EnvironmentKey {
    static let defaultValue: LibraryContentKind? = nil
}

extension EnvironmentValues {
    var paneContentKindSwitcher: PaneContentKindSwitcher? {
        get { self[PaneContentKindSwitcherKey.self] }
        set { self[PaneContentKindSwitcherKey.self] = newValue }
    }

    /// The EXPLICIT content kind a workspace/user set for THIS library pane
    /// (`PaneConfig.libraryContentKind`, decoded), published by
    /// `ContentView.paneNodeView` — mirrors `\.paneLibraryLayout`'s shape
    /// exactly (`ViewDisplayMode.swift`), the same mechanism for the sibling
    /// per-pane-config field. nil everywhere outside a library leaf's own
    /// slot, or when that leaf has never had an explicit kind set.
    var paneContentKind: LibraryContentKind? {
        get { self[PaneContentKindKey.self] }
        set { self[PaneContentKindKey.self] = newValue }
    }
}

private struct IsSolePaneKey: EnvironmentKey {
    static let defaultValue = false
}

extension EnvironmentValues {
    /// True when this pane is the window's ONLY pane — the head then collapses its close affordance
    /// (nothing to close; the ≥1-pane invariant), so a single pane wears the least chrome (CD
    /// 2026-09-16: "collapse better if there is just one").
    var isSolePane: Bool {
        get { self[IsSolePaneKey.self] }
        set { self[IsSolePaneKey.self] = newValue }
    }
}
