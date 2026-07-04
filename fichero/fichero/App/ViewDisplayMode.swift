import SwiftUI

/// View display modes (Icon/List/Table/Map) — universal across content types.
///
/// Extracted from the retired `MainToolbar.swift` (#3032): the `MainToolbar`
/// view was orphaned and deleted, but this enum is the shared view-mode model
/// (used by the toolbar picker, ContentView routing, the View menu, and
/// persistence), so it lives here alongside the sibling view-mode enums in
/// `ViewSettings.swift`.
enum ViewDisplayMode: String, CaseIterable, Identifiable {
    case icon = "Icon"
    case list = "List"
    case table = "Table"
    case map = "Map"
    // RETIRED 3D "Space" / Mind Palace alias. The RealityKit renderer was
    // removed (3D rooms superseded by the live 2D spatial library view). The
    // case is retained ONLY so persisted/@SceneStorage "RealityKit" rawValues
    // still decode and migrate to .map via normalizedViewDisplayMode(). Hidden
    // from every picker/menu; never offered by availableViewDisplayModes.
    case realitykit = "RealityKit"
    // DEPRECATED legacy alias (#2667). "Spatial (2D)" merged into Canvas (.map):
    // both now render Spatial2DCanvas off the shared canvasLayoutStore. The case
    // is retained ONLY so persisted/@SceneStorage "Spatial" rawValues still decode
    // and can be migrated to .map by normalizedViewDisplayMode(). It is hidden from
    // every picker/menu and never offered by availableViewDisplayModes.
    case spatial = "Spatial"
    case workspace = "Workspace"

    /// User-selectable cases (excludes the retired `.spatial` + `.realitykit`
    /// decode-only aliases, #2667).
    static var selectableCases: [ViewDisplayMode] {
        allCases.filter { $0 != .spatial && $0 != .realitykit }
    }

    var id: String { rawValue }

    /// User-facing label shown in menus/pickers. rawValue is preserved for
    /// persistence/XCUITest hooks — only label changes here.
    var label: String {
        switch self {
        case .table: "Columns"
        case .map: "Canvas"
        case .realitykit: "Space"
        default: rawValue
        }
    }

    var icon: String {
        switch self {
        case .icon: "square.grid.2x2"
        case .list: "list.bullet"
        case .table: "tablecells"
        case .map: "map"
        case .realitykit: "cube.transparent"
        case .spatial: "square.3.layers.3d"
        case .workspace: "square.stack.3d.up"
        }
    }

    var description: String {
        switch self {
        case .icon: "Grid of icons"
        case .list: "Linear list"
        case .table: "Column view"
        case .map: "Canvas / node map"
        case .realitykit: "3D space view"
        case .spatial: "Spatial collection view"
        case .workspace: "Workspace collection view"
        }
    }
}

// `.table` renders as the multi-column table view (`LibraryView.tableView`);
// its user-facing name is "Column" (Mail-style, #1613) while the enum case and
// rawValue stay `.table`/"Table".
