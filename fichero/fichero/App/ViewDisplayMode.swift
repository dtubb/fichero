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

    /// Decode that migrates legacy persisted/`@SceneStorage`/`@AppStorage`
    /// rawValues (#3081). The old cases are gone, so this init folds their
    /// stored strings onto the new ones: `"Map"` (old Canvas) and `"Spatial"`
    /// (old 2D spatial, merged into Canvas) → `.canvas`; `"RealityKit"` (old 3D
    /// Mind Palace render) → `.space`. Without this, those strings would decode
    /// to `nil` and silently reset to `.icon`. The synthesized `rawValue` getter
    /// is unaffected, so values still round-trip to the canonical rawValue.
    init?(rawValue: String) {
        switch rawValue {
        case "Icon": self = .icon
        case "List": self = .list
        case "Table": self = .table
        case "Canvas", "Map", "Spatial": self = .canvas
        case "Space", "RealityKit": self = .space
        case "Workspace": self = .workspace
        default: return nil
        }
    }

    /// User-selectable cases: the coherent view-mode set (#3081). `.workspace`
    /// is offered separately via `availableViewDisplayModes` behind its feature
    /// gate, so it is not part of the base selectable set.
    static var selectableCases: [ViewDisplayMode] {
        [.icon, .list, .table, .canvas, .space]
    }

    var id: String { rawValue }

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
