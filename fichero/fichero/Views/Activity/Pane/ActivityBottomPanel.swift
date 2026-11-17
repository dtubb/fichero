import Charts
import SwiftUI

/// The Activity window's foot (`activity.window.bottom-panel`, decision 25, #6588): per tab, a graph and its figures
/// together, read from the engine's history (`GET /api/activity/history`). Runs and Files: pages done per minute over the
/// last hour; Cost: dollars per minute and today's by provider; Where: pages by where they ran. A main window's pane keeps
/// the one status line instead.
struct ActivityBottomPanel: View {
    let tab: ActivityPane.Tab
    let history: ActivityHistoryFigures
    /// The sidebar's pick under Where ("model:…", "provider:…", "place:…"): its own pages and calls are drawn.
    var pick: String?
    /// The rows listed now, for the counts the history does not hold (running, waiting, need you).
    let rows: [ActivityMonitorRow]
    /// Whether the graphs fill the centre (`activity.graphs.own-pane`, decision 41), and the press that turns it.
    var isFull = false
    var toggleFull: () -> Void = {}

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text(Self.pickFigures(pick, history: history) ?? Self.figures(tab: tab, history: history, rows: rows))
                    .font(.callout).monospacedDigit().foregroundStyle(.secondary).lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Button(action: toggleFull) {
                    Label(isFull ? "Show the Table" : "Graphs Full Size",
                          systemImage: isFull ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right")
                }
                .labelStyle(.iconOnly).buttonStyle(.borderless)
                .help(isFull ? "Show the table again" : "Make the graphs fill the window")
                .accessibilityLabel(isFull ? "Show the Table" : "Graphs Full Size")
                .accessibilityIdentifier("activity.bottomPanel.full")
            }
            if Self.isEmpty(history) {
                Text("No work in the last hour").foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                graph.frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
        // It fills what `ActivityGraphsSplitStack` gives it, never sizing the centre by its chart or its figures (#6661).
        .frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity)
        .background(.bar)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("activity.bottomPanel")
    }

    @ViewBuilder
    private var graph: some View {
        if let picked = Self.pickSeries(pick, history: history) {
            Chart {
                ForEach(picked) { minute in
                    BarMark(x: .value("Minute", minute.start, unit: .minute), y: .value("Pages", minute.pages))
                        .foregroundStyle(by: .value("Count", "Pages"))
                    LineMark(x: .value("Minute", minute.start, unit: .minute), y: .value("Calls", minute.calls))
                        .foregroundStyle(by: .value("Count", "Calls"))
                }
            }
            .accessibilityLabel("Pages and calls per minute on the model picked, the last hour")
        } else {
            tabGraph
        }
    }

    @ViewBuilder
    private var tabGraph: some View {
        switch tab {
        case .recipes:
            Chart(Self.recipePoints(history)) { point in
                BarMark(x: .value("Minute", point.start, unit: .minute), y: .value("Pages", point.pages))
                    .foregroundStyle(by: .value("Recipe", point.recipe))
            }
            .accessibilityLabel("Pages done per minute by recipe, the last hour")
        case .runs, .files, .archived:
            Chart(history.minutes) { minute in
                BarMark(x: .value("Minute", minute.start, unit: .minute), y: .value("Pages", minute.pagesDone))
                    .foregroundStyle(.green)
                if minute.pagesFailed > 0 {
                    BarMark(x: .value("Minute", minute.start, unit: .minute), y: .value("Pages", minute.pagesFailed))
                        .foregroundStyle(.red)
                }
            }
            .accessibilityLabel("Pages done per minute, the last hour")
        case .cost:
            Chart(history.minutes) { minute in
                AreaMark(x: .value("Minute", minute.start, unit: .minute), y: .value("Dollars", minute.spendUsd))
            }
            .accessibilityLabel("Dollars spent per minute, the last hour")
        case .place:
            Chart(Self.places(history), id: \.word) { place in
                BarMark(x: .value("Pages", place.pages), y: .value("Where", place.word))
            }
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
            total.byRecipe = Self.mergedSeries(total.byRecipe, other.byRecipe)
            total.byModel = Self.mergedSeries(total.byModel, other.byModel)
            total.todaySpendUsd += other.todaySpendUsd
            total.todaySpendByProvider.merge(other.todaySpendByProvider, uniquingKeysWith: +)
        }
        return total
    }

    /// One minute of the graph by recipe: a stacked bar's part.
    struct RecipePoint: Identifiable, Equatable {
        let start: Date
        let recipe: String
        let pages: Int
        var id: String { "\(start.timeIntervalSince1970)|\(recipe)" }
    }

    /// The Recipes graph's parts: each recipe's pages in each minute it did any.
    static func recipePoints(_ history: ActivityHistoryFigures) -> [RecipePoint] {
        history.byRecipe.flatMap { series in
            zip(history.minutes, series.pages).compactMap { minute, pages in
                pages > 0 ? RecipePoint(start: minute.start, recipe: series.key, pages: pages) : nil
            }
        }
    }

    /// One minute of a picked model's, provider's or place's own work.
    struct PickMinute: Identifiable, Equatable {
        let start: Date
        var pages = 0
        var calls = 0
        var id: Date { start }
    }

    /// The picked model's (its id), provider's (every model under it) or place's (every model there) pages and
    /// calls per minute, or nil when the pick is not under Where. A model's id is "place|provider|name", as the tree's.
    static func pickSeries(_ pick: String?, history: ActivityHistoryFigures) -> [PickMinute]? {
        guard let pick else { return nil }
        let matches: (String) -> Bool
        if pick.hasPrefix("model:") {
            let id = String(pick.dropFirst(6))
            matches = { $0 == id }
        } else if pick.hasPrefix("provider:") {
            let name = String(pick.dropFirst(9))
            matches = { key in
                key.split(separator: "|", omittingEmptySubsequences: false).dropFirst().first.map(String.init) == name
            }
        } else if pick.hasPrefix("place:") {
            let place = String(pick.dropFirst(6))
            matches = { $0.hasPrefix(place + "|") }
        } else {
            return nil
        }
        var out = history.minutes.map { PickMinute(start: $0.start) }
        for series in history.byModel where matches(series.key) {
            for (index, pages) in series.pages.enumerated() where index < out.count { out[index].pages += pages }
            for (index, calls) in series.calls.enumerated() where index < out.count { out[index].calls += calls }
        }
        return out
    }

    /// The pick's figures: "12 pages · 30 calls in the last hour"; nil when the pick is not under Where.
    static func pickFigures(_ pick: String?, history: ActivityHistoryFigures) -> String? {
        guard let minutes = pickSeries(pick, history: history) else { return nil }
        let pages = minutes.reduce(0) { $0 + $1.pages }
        let calls = minutes.reduce(0) { $0 + $1.calls }
        return "\(pages) pages · \(calls) calls in the last hour"
    }

    /// Two projects' series as one: by key, minute by minute added (the windows end at the same minute).
    static func mergedSeries(_ one: [ActivityHistoryFigures.Series], _ other: [ActivityHistoryFigures.Series])
        -> [ActivityHistoryFigures.Series] {
        var out = one
        for series in other {
            guard let index = out.firstIndex(where: { $0.key == series.key }) else { out.append(series); continue }
            let add: ([Int], [Int]) -> [Int] = { lhs, rhs in
                (0..<max(lhs.count, rhs.count)).map { (lhs.indices.contains($0) ? lhs[$0] : 0)
                    + (rhs.indices.contains($0) ? rhs[$0] : 0) }
            }
            out[index].pages = add(out[index].pages, series.pages)
            out[index].calls = add(out[index].calls, series.calls)
        }
        return out
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
        case .archived:
            return "\(rows.count) archived · \(done) pages done in the last hour"
        case .recipes:
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
