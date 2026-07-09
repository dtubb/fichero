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
    /// Legacy persisted alias: decode/normalize to `.canvas`, never present as
    /// a live selectable mode (#3199).
    case workspace = "Workspace"

    /// User-selectable cases: the coherent live view-mode set (#3081/#3199).
    static var selectableCases: [ViewDisplayMode] {
        [.icon, .list, .table, .canvas, .space]
    }

    var id: String { rawValue }

    static func persisted(_ rawValue: String) -> ViewDisplayMode? {
        switch rawValue {
        case Self.icon.rawValue: .icon
        case Self.list.rawValue: .list
        case Self.table.rawValue: .table
        case Self.canvas.rawValue, "Map", "Spatial", Self.workspace.rawValue: .canvas
        case Self.space.rawValue, "RealityKit": .space
        default: nil
        }
    }

    /// The `LibraryLayout` (View-menu twin) this display mode maps to. The single
    /// source of truth for the ViewDisplayMode → LibraryLayout bridge (#3088),
    /// replacing three hand-copied switches. `.canvas`/`.workspace` both surface
    /// as `.canvas`; `.space` is its own case so ⌘5 Space doesn't collapse to it.
    var libraryLayout: LibraryLayout {
        switch self {
        case .icon: .icons
        case .list: .list
        case .table: .table
        case .space: .space
        case .canvas, .workspace: .canvas
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
