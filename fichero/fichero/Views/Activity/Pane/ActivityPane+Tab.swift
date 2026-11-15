import Foundation

// The sidebar's items, split out of ActivityPane.swift (SwiftLint's size limits).

extension ActivityPane {
    /// The window's sidebar items, one table (`activity.window.sidebar`, decision 32; were the toolbar's tabs, decision 23):
    /// each a grouping and a column set over the same rows. Runs: what is working and what needs me; Files: what happened to
    /// my pages; Cost: what it spends; Where: where it runs; Archived: the rows put away, and only those.
    enum Tab: String, CaseIterable, Identifiable, Codable {
        case runs, files, recipes, cost, place = "where", archived

        var id: String { rawValue }

        var title: String {
            switch self {
            case .runs: "Runs"
            case .files: "Files"
            case .recipes: "Recipes"
            case .cost: "Cost"
            case .place: "Where"
            case .archived: "Archived"
            }
        }

        var icon: String {
            switch self {
            case .runs: "list.bullet.indent"
            case .files: "doc.on.doc"
            case .recipes: "list.bullet.rectangle"
            case .cost: "dollarsign.circle"
            case .place: "desktopcomputer"
            case .archived: "archivebox"
            }
        }

        var grouping: Grouping { self == .files ? .file : .run }

        /// The columns the tab shows until a person changes them.
        var columns: [Column] {
            switch self {
            case .runs: [.source, .name, .state, .trail, .time, .cost]
            case .files: [.name, .state, .trail, .started]
            case .recipes: [.name, .state, .model, .time, .cost]
            case .cost: [.source, .name, .model, .tokens, .time, .cost, .toFinish]
            case .place: [.source, .name, .runsOn, .lane, .state]
            case .archived: [.source, .name, .state, .started, .time, .cost]
            }
        }

        /// The sidebar's sections (`activity.window.sidebar`): the work, then the resources it uses; Archived below them.
        static let sidebarWork: [Tab] = [.runs, .files, .recipes]
        static let sidebarResources: [Tab] = [.cost, .place]

        /// The tab a grouping chosen elsewhere (View › Activity ▸, a main window's lens) lands on.
        static func of(_ grouping: Grouping) -> Tab { grouping == .file ? .files : .runs }
    }
}
