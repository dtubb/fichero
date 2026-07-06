import SwiftUI

/// View display modes (Icon/List/Table/Canvas/Space) — universal across content
/// types.
///
/// Extracted from the retired `MainToolbar.swift` (#3032): the `MainToolbar`
/// view was orphaned and deleted, but this enum is the shared view-mode model
/// (used by the toolbar picker, ContentView routing, the View menu, and
/// persistence), so it lives here alongside the sibling view-mode enums in
/// `ViewSettings.swift`.
///
/// Canvas & Space foundation (#3081): `.canvas` is the 2D positioned-node view
/// (renamed from the old `.map`); `.space` is the 3D view. Both are
/// renderer-agnostic here — the enum is the coherent model; the P2/P3 renderers
/// are wired separately.
enum ViewDisplayMode: String, CaseIterable, Identifiable {
    case icon = "Icon"
    case list = "List"
    case table = "Table"
    case canvas = "Canvas"
    case space = "Space"
    case workspace = "Workspace"

    // Decoding uses the synthesized `init?(rawValue:)` — exact match only. The
    // library data isn't in production use, so legacy strings ("Map"/"Spatial"/
    // "RealityKit") are intentionally NOT migrated; they decode to nil and reset
    // to the default rather than carry a back-compat shim (Daniel, 2026-07-05).

    /// User-selectable cases: the coherent view-mode set (#3081). `.workspace`
    /// is offered separately via `availableViewDisplayModes` behind its feature
    /// gate, so it is not part of the base selectable set.
    static var selectableCases: [ViewDisplayMode] {
        [.icon, .list, .table, .canvas, .space]
    }

    var id: String { rawValue }

    /// The `LibraryLayout` (View-menu twin) this display mode maps to. The single
    /// source of truth for the ViewDisplayMode → LibraryLayout bridge (#3088),
    /// replacing three hand-copied switches. `.canvas`/`.workspace` both surface
    /// as `.map`; `.space` is its own case so ⌘5 Space doesn't collapse to Canvas.
    var libraryLayout: LibraryLayout {
        switch self {
        case .icon: .icons
        case .list: .list
        case .table: .table
        case .space: .space
        case .canvas, .workspace: .map
        }
    }

    /// User-facing label shown in menus/pickers. rawValue is preserved for
    /// persistence/XCUITest hooks — only label changes here.
    var label: String {
        switch self {
        case .table: "Columns"
        default: rawValue
        }
    }

    var icon: String {
        switch self {
        case .icon: "square.grid.2x2"
        case .list: "list.bullet"
        case .table: "tablecells"
        case .canvas: "map"
        case .space: "cube.transparent"
        case .workspace: "square.stack.3d.up"
        }
    }

    var description: String {
        switch self {
        case .icon: "Grid of icons"
        case .list: "Linear list"
        case .table: "Column view"
        case .canvas: "Canvas / node map"
        case .space: "3D space view"
        case .workspace: "Workspace collection view"
        }
    }
}

// `.table` renders as the multi-column table view (`LibraryView.tableView`);
// its user-facing name is "Column" (Mail-style, #1613) while the enum case and
// rawValue stay `.table`/"Table".
