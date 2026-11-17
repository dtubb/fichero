import Charts
import SwiftUI

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

#Preview("Timeline, nothing drawn") {
    ActivityTimelineView(rows: [])
        .frame(width: 480, height: 240)
}
