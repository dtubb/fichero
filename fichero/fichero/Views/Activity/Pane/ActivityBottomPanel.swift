import Charts
import SwiftUI

/// The Activity window's foot (`activity.window.bottom-panel`, decision 25, #6588): per tab, a graph and its figures
/// together, read from the engine's history (`GET /api/activity/history`). Runs and Files: pages done per minute over the
/// last hour; Cost: dollars per minute and today's by provider; Where: pages by where they ran. A main window's pane keeps
/// the one status line instead.
struct ActivityBottomPanel: View {
    let tab: ActivityPane.Tab
    let history: ActivityHistoryFigures
    /// The rows listed now, for the counts the history does not hold (running, waiting, need you).
    let rows: [ActivityMonitorRow]

    var body: some View {
        HStack(alignment: .center, spacing: 16) {
            if Self.isEmpty(history) {
                Text("No work in the last hour").foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                graph.frame(width: 260, height: 44)
            }
            Text(Self.figures(tab: tab, history: history, rows: rows))
                .font(.callout).monospacedDigit().foregroundStyle(.secondary).lineLimit(2)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
        .background(.bar)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("activity.bottomPanel")
    }

    @ViewBuilder
    private var graph: some View {
        switch tab {
        case .runs, .files:
            Chart(history.minutes) { minute in
                BarMark(x: .value("Minute", minute.start, unit: .minute), y: .value("Pages", minute.pagesDone))
                    .foregroundStyle(.green)
                if minute.pagesFailed > 0 {
                    BarMark(x: .value("Minute", minute.start, unit: .minute), y: .value("Pages", minute.pagesFailed))
                        .foregroundStyle(.red)
                }
            }
            .chartXAxis(.hidden).chartYAxis(.hidden)
            .accessibilityLabel("Pages done per minute, the last hour")
        case .cost:
            Chart(history.minutes) { minute in
                AreaMark(x: .value("Minute", minute.start, unit: .minute), y: .value("Dollars", minute.spendUsd))
            }
            .chartXAxis(.hidden).chartYAxis(.hidden)
            .accessibilityLabel("Dollars spent per minute, the last hour")
        case .place:
            Chart(Self.places(history), id: \.word) { place in
                BarMark(x: .value("Pages", place.pages), y: .value("Where", place.word))
            }
            .chartXAxis(.hidden)
            .accessibilityLabel("Pages done by where they ran, the last hour")
        }
    }

    // MARK: - The words and series, pure (`ActivityBottomPanelTests`)

    /// Many projects' histories as one: minute by minute summed, the places and providers added.
    static func merged(_ histories: [ActivityHistoryFigures]) -> ActivityHistoryFigures {
        guard var total = histories.first else { return ActivityHistoryFigures() }
        for other in histories.dropFirst() {
            var byStart = Dictionary(total.minutes.map { ($0.start, $0) }, uniquingKeysWith: { first, _ in first })
            for minute in other.minutes {
                var sum = byStart[minute.start] ?? ActivityHistoryFigures.Minute(start: minute.start)
                sum.pagesDone += minute.pagesDone
                sum.pagesFailed += minute.pagesFailed
                sum.spendUsd += minute.spendUsd
                sum.tokens += minute.tokens
                byStart[minute.start] = sum
            }
            total.minutes = byStart.values.sorted { $0.start < $1.start }
            total.byRuntime.merge(other.byRuntime, uniquingKeysWith: +)
            total.todaySpendUsd += other.todaySpendUsd
            total.todaySpendByProvider.merge(other.todaySpendByProvider, uniquingKeysWith: +)
        }
        return total
    }

    static func isEmpty(_ history: ActivityHistoryFigures) -> Bool {
        history.minutes.allSatisfy { $0.pagesDone == 0 && $0.pagesFailed == 0 && $0.spendUsd == 0 }
    }

    /// The places in the Where graph, in a fixed order, each with its pages.
    static func places(_ history: ActivityHistoryFigures) -> [(word: String, pages: Int)] {
        [("this-mac", "This Mac"), ("other-mac", "Other Mac"), ("cloud", "Cloud"), ("cluster", "Cluster")]
            .map { (word: $0.1, pages: history.byRuntime[$0.0] ?? 0) }
    }

    /// The tab's figures, at most two short lines, counts as figures (`activity.pane.text-budget`).
    static func figures(tab: ActivityPane.Tab, history: ActivityHistoryFigures, rows: [ActivityMonitorRow]) -> String {
        let done = history.minutes.map(\.pagesDone).reduce(0, +)
        let failed = history.minutes.map(\.pagesFailed).reduce(0, +)
        switch tab {
        case .runs:
            let running = rows.filter { $0.phase == .running }.count
            let waiting = rows.filter { $0.phase == .waiting }.count
            let needYou = rows.filter { $0.phase == .failed || $0.phase == .partial || $0.phase == .paused }.count
            return "\(running) running · \(waiting) waiting · \(needYou) need you\n\(done) pages done in the last hour"
        case .files:
            return "\(done) pages done · \(failed) failed in the last hour"
        case .cost:
            let providers = history.todaySpendByProvider.sorted { $0.value > $1.value }
                .map { "\($0.key) \(String(format: "$%.2f", $0.value))" }
            let tokens = history.minutes.map(\.tokens).reduce(0, +)
            let today = String(format: "$%.2f today", history.todaySpendUsd)
            return ([today] + providers).joined(separator: " · ") + "\n\(tokens.formatted()) tokens in the last hour"
        case .place:
            return places(history).map { "\($0.word) \($0.pages == 0 ? "—" : "\($0.pages)")" }.joined(separator: " · ")
        }
    }
}

#Preview("Bottom panel, Runs") {
    let now = Date()
    let minutes = (0..<60).map { index in
        ActivityHistoryFigures.Minute(start: now.addingTimeInterval(Double(index - 59) * 60), pagesDone: index % 7,
                               pagesFailed: index % 13 == 0 ? 1 : 0, spendUsd: Double(index % 5) * 0.01, tokens: index * 40)
    }
    let history = ActivityHistoryFigures(minutes: minutes, byRuntime: ["this-mac": 120, "cloud": 30], todaySpendUsd: 0.5,
                                  todaySpendByProvider: ["OpenRouter": 0.42, "Gemini": 0.08])
    VStack(spacing: 0) {
        ForEach(ActivityPane.Tab.allCases) { tab in
            ActivityBottomPanel(tab: tab, history: history, rows: [])
            Divider()
        }
    }
    .frame(width: 720)
}
