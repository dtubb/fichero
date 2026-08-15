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
    /// Finder-style Miller column browser (#4160 step 4) — an ADDITIONAL
    /// mode; `.table` keeps its 3-level outline (the user's decision).
    case columns = "MillerColumns"
    /// Dataset renderers (Stage 2), each a FULL top-level view mode taking
    /// over the library like icon/canvas (Daniel 2026-08-14: "data is not
    /// an independent view … the independent views are timeline, card,
    /// grid, map"). The geo mode's rawValue is NOT "Map": that legacy alias
    /// normalizes to `.canvas` in `persisted(_:)`.
    /// The spreadsheet over typed attributes ("grid is more like
    /// spreadsheet", Daniel 2026-08-14). rawValue avoids the icon-grid
    /// word "Grid" for persistence clarity.
    case grid = "DataGrid"
    case cards = "Cards"
    case timeline = "Timeline"
    case calendar = "CalendarGrid"
    case geoMap = "GeoMap"
    /// Legacy persisted alias: decode/normalize to `.canvas`, never present as
    /// a live selectable mode (#3199).
    case workspace = "Workspace"

    /// User-selectable cases: the coherent live view-mode set (#3081/#3199).
    static var selectableCases: [ViewDisplayMode] {
        [.icon, .list, .table, .columns, .grid, .cards, .timeline, .calendar, .geoMap, .canvas, .space]
    }

    var id: String { rawValue }

    /// Picker grouping (Daniel 2026-08-14: "two groups, like Finder style,
    /// Canvas style, and then the dataset style").
    enum Group: String, CaseIterable {
        case browse = "Browse"
        case dataset = "Dataset"
        case canvas = "Canvas"
    }

    var group: Group {
        switch self {
        case .icon, .list, .table, .columns: .browse
        case .grid, .cards, .timeline, .calendar, .geoMap: .dataset
        case .canvas, .space, .workspace: .canvas
        }
    }

    static func persisted(_ rawValue: String) -> ViewDisplayMode? {
        switch rawValue {
        case Self.icon.rawValue: .icon
        case Self.list.rawValue: .list
        case Self.table.rawValue: .table
        case Self.canvas.rawValue, "Map", "Spatial", Self.workspace.rawValue: .canvas
        case Self.space.rawValue, "RealityKit": .space
        case Self.columns.rawValue: .columns
        case Self.grid.rawValue: .grid
        case Self.cards.rawValue: .cards
        case Self.timeline.rawValue: .timeline
        case Self.calendar.rawValue: .calendar
        case Self.geoMap.rawValue: .geoMap
        // The short-lived combined "Data" mode (29090f32f) decodes to cards.
        case "Dataset": .cards
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
        case .columns: .columns
        case .grid: .grid
        case .cards: .cards
        case .timeline: .timeline
        case .calendar: .calendar
        case .geoMap: .geoMap
        case .space: .space
        case .canvas, .workspace: .canvas
        }
    }

    /// User-facing label shown in menus/pickers. rawValue is preserved for
    /// persistence/XCUITest hooks — only label changes here.
    var label: String {
        switch self {
        // A REAL Miller-columns mode exists now (#4160 step 4), so the
        // table reverts to its honest name — two modes named "Columns"
        // would be actively misleading (supersedes the #1613 rename).
        case .table: "Table"
        case .columns: "Columns"
        case .grid: "Grid"
        case .calendar: "Calendar"
        case .geoMap: "Map"
        default: rawValue
        }
    }

    var icon: String {
        switch self {
        case .icon: "square.grid.2x2"
        case .list: "list.bullet"
        case .table: "tablecells"
        case .columns: "rectangle.split.3x1"
        case .grid: "tablecells.badge.ellipsis"
        case .cards: "rectangle.grid.2x2"
        case .timeline: "chart.bar.xaxis"
        case .calendar: "calendar"
        case .geoMap: "mappin.and.ellipse"
        case .canvas: "map"
        case .space: "cube.transparent"
        case .workspace: "square.stack.3d.up"
        }
    }

    var description: String {
        switch self {
        case .icon: "Grid of icons"
        case .list: "Linear list"
        case .table: "Multi-column table"
        case .columns: "Finder-style column browser"
        case .grid: "Spreadsheet of typed attributes"
        case .cards: "Cards over typed attributes"
        case .timeline: "Entries by their date attribute"
        case .calendar: "Month grid over the date attribute"
        case .geoMap: "Pins from the geo attribute"
        case .canvas: "Canvas / node map"
        case .space: "3D space view"
        case .workspace: "Workspace collection view"
        }
    }
}

// `.table` renders as the multi-column table view (`LibraryView.tableView`);
// its user-facing name is "Column" (Mail-style, #1613) while the enum case and
// rawValue stay `.table`/"Table".
