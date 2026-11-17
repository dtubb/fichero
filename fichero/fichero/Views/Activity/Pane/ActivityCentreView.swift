import Charts
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
    /// rows are work with a start and an end (Runs, Files, Archived, Where). Recipes' Visual is a run's node graph, and
    /// Cost has none: both offer Table and Graph.
    static func offered(for tab: ActivityPane.Tab) -> [ActivityCentreView] {
        switch tab {
        case .runs, .files, .archived, .place: [.table, .graph, .visual]
        case .recipes, .cost: [.table, .graph]
        }
    }
}

/// The Visual view's timeline (`activity.window.centre-views`): each row of work a bar from its start to its end, on
/// the line of its lane (or its model), coloured by its state. Pure, so `ActivityCentreViewsTests` reads it.
enum ActivityTimeline {
    enum Lines: String, CaseIterable, Identifiable {
        case lane, model
        var id: String { rawValue }
        var title: String { self == .lane ? "By Lane" : "By Model" }
    }

    struct Bar: Identifiable, Equatable {
        let id: String
        let line: String
        let name: String
        let start: Date
        let end: Date
        let state: String
    }

    /// The bars of the rows and their children: a row with no start is not drawn; a row still going ends now; one that
    /// ended without an end time ends at its start plus its seconds. The work the rows hold, not their grouping rows: a
    /// row with children is drawn by its children.
    static func bars(_ rows: [ActivityMonitorRow], by lines: Lines, now: Date) -> [Bar] {
        rows.flatMap { row -> [Bar] in
            if let children = row.children, !children.isEmpty { return bars(children, by: lines, now: now) }
            guard let start = row.started else { return [] }
            let measured = row.seconds.map { start.addingTimeInterval($0) }
            let end = row.ended ?? (row.phase == .running ? now : measured ?? now)
            let line = lines == .lane ? (row.lane ?? "Other") : (row.model ?? "No model")
            return [Bar(id: row.id, line: line, name: row.name, start: start,
                        end: max(end, start.addingTimeInterval(1)), state: row.phase.word)]
        }
        .sorted { $0.start < $1.start }
    }
}

/// The Visual view: the timeline, by lane or by model.
struct ActivityTimelineView: View {
    let rows: [ActivityMonitorRow]
    @State private var lines: ActivityTimeline.Lines = .lane

    var body: some View {
        let bars = ActivityTimeline.bars(rows, by: lines, now: Date())
        VStack(alignment: .leading, spacing: 8) {
            Picker("Lines", selection: $lines) {
                ForEach(ActivityTimeline.Lines.allCases) { Text($0.title).tag($0) }
            }
            .pickerStyle(.segmented).labelsHidden().fixedSize()
            if bars.isEmpty {
                Text("Nothing with a start time to draw").foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                Chart(bars) { bar in
                    BarMark(xStart: .value("Start", bar.start), xEnd: .value("End", bar.end),
                            y: .value("Line", bar.line))
                        .foregroundStyle(by: .value("State", bar.state))
                        .accessibilityLabel(bar.name)
                }
                .accessibilityLabel(lines == .lane ? "Work over time by lane" : "Work over time by model")
            }
        }
        .padding(12)
        .frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity)
        .accessibilityIdentifier("activity.centre.visual")
    }
}
