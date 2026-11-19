import SwiftUI

/// The centre's views of what the sidebar picked (`activity.window.centre-views`, decisions 38-39, #6588): Table (the
/// rows), Graph (the item's graphs over time, full size) and Visual (the work drawn: a timeline of bars per lane or per
/// model).
enum ActivityCentreView: String, Codable, CaseIterable, Identifiable {
    case table, graph, visual

    var id: String { rawValue }

    var title: String {
        switch self {
        case .table: "Table"
        case .graph: "Graph"
        case .visual: "Visual"
        }
    }

    var symbol: String {
        switch self {
        case .table: "tablecells"
        case .graph: "chart.bar.xaxis"
        case .visual: "chart.bar.doc.horizontal"
        }
    }

    /// The views that mean something for a sidebar item: every item has Table and Graph; Visual is offered where the
    /// rows are work with a start and an end (Runs, Files, Archived, Where: a timeline) and on Recipes (each recipe's
    /// newest run as its steps, `ActivityRunGraph`). Cost has none.
    static func offered(for tab: ActivityPane.Tab) -> [ActivityCentreView] {
        switch tab {
        case .runs, .files, .archived, .place, .recipes: [.table, .graph, .visual]
        case .cost: [.table, .graph]
        }
    }
}

#Preview("Centre views") {
    Picker("View", selection: .constant(ActivityCentreView.table)) {
        ForEach(ActivityCentreView.allCases) { Label($0.title, systemImage: $0.symbol).tag($0) }
    }
    .pickerStyle(.segmented)
    .padding()
}
