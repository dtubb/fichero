import SwiftUI

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
