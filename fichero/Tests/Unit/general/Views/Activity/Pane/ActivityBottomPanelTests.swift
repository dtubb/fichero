@testable import Fichero
import Foundation
import Testing

/// `activity.window.bottom-panel` (#6588, decision 25; spec docs/contributor_manual/specs/ui/activity-pane.md): the window's
/// foot shows a graph and its figures per tab, from the engine's history, the projects' answers summed.
@MainActor
struct ActivityBottomPanelTests {
    private let start = Date(timeIntervalSince1970: 1_800_000_000)

    private func minutes(_ pages: [Int], spend: Double = 0) -> [ActivityHistoryFigures.Minute] {
        pages.enumerated().map {
            ActivityHistoryFigures.Minute(start: start.addingTimeInterval(Double($0.offset) * 60), pagesDone: $0.element,
                                          spendUsd: spend, tokens: 10)
        }
    }

    @Test("two projects' histories are one: minute by minute summed, places and providers added")
    func merged() {
        let one = ActivityHistoryFigures(minutes: minutes([3, 0, 2]), byRuntime: ["this-mac": 5], todaySpendUsd: 0.1,
                                  todaySpendByProvider: ["OpenRouter": 0.1])
        let two = ActivityHistoryFigures(minutes: minutes([1, 4, 0]), byRuntime: ["this-mac": 2, "cloud": 3], todaySpendUsd: 0.2,
                                  todaySpendByProvider: ["OpenRouter": 0.15, "Gemini": 0.05])
        let total = ActivityBottomPanel.merged([one, two])
        #expect(total.minutes.map(\.pagesDone) == [4, 4, 2])
        #expect(total.byRuntime == ["this-mac": 7, "cloud": 3])
        #expect(abs(total.todaySpendUsd - 0.3) < 1e-9)
        #expect(abs((total.todaySpendByProvider["OpenRouter"] ?? 0) - 0.25) < 1e-9)
    }

    @Test("each tab's figures: counts, pages, today's spend by provider, each place or a dash")
    func figures() {
        let history = ActivityHistoryFigures(minutes: minutes([10, 20]), byRuntime: ["this-mac": 30],
                                      todaySpendUsd: 0.5, todaySpendByProvider: ["OpenRouter": 0.42, "Gemini": 0.08])
        let rows = [ActivityPaneFixture.row("r", .running), ActivityPaneFixture.row("f", .failed)]
        #expect(ActivityBottomPanel.figures(tab: .runs, history: history, rows: rows)
            == "1 running · 0 waiting · 1 need you\n30 pages done in the last hour")
        #expect(ActivityBottomPanel.figures(tab: .files, history: history, rows: rows) == "30 pages done · 0 failed in the last hour")
        #expect(ActivityBottomPanel.figures(tab: .cost, history: history, rows: rows)
            == "$0.50 today · OpenRouter $0.42 · Gemini $0.08\n20 tokens in the last hour")
        #expect(ActivityBottomPanel.figures(tab: .place, history: history, rows: rows)
            == "This Mac 30 · Other Mac — · Cloud — · Cluster —")
    }

    @Test("an hour with no work draws no graph: it says so in one line")
    func empty() {
        #expect(ActivityBottomPanel.isEmpty(ActivityHistoryFigures(minutes: minutes([0, 0, 0]))))
        #expect(!ActivityBottomPanel.isEmpty(ActivityHistoryFigures(minutes: minutes([0, 1]))))
    }

    // `activity.window.graph-on-every-view` (decision 34): Recipes graphs pages per minute by recipe; a model, provider or
    // place picked under Where graphs its own pages and calls per minute.
    private func series() -> ActivityHistoryFigures {
        var history = ActivityHistoryFigures(minutes: minutes([0, 0, 0]))
        history.byRecipe = [.init(key: "Letters", pages: [2, 0, 1]), .init(key: "Read the letters", pages: [0, 3, 0])]
        history.byModel = [
            .init(key: "this-mac|Kraken|blla", pages: [2, 0, 1], calls: [0, 0, 0]),
            .init(key: "cloud|Anthropic|claude", pages: [0, 3, 0], calls: [4, 6, 0]),
            .init(key: "cloud|OpenAI|gpt", pages: [0, 1, 0], calls: [0, 1, 0])
        ]
        return history
    }

    @Test("the Recipes graph stacks each recipe's pages in the minutes it did any")
    func recipesGraph() {
        let points = ActivityBottomPanel.recipePoints(series())
        #expect(points.map(\.recipe) == ["Letters", "Letters", "Read the letters"])
        #expect(points.map(\.pages) == [2, 1, 3])
    }

    @Test("a picked model graphs its own pages and calls; a provider or a place sums the models under it")
    func pickedModelGraph() {
        let history = series()
        let model = ActivityBottomPanel.pickSeries("model:cloud|Anthropic|claude", history: history)
        #expect(model?.map(\.pages) == [0, 3, 0] && model?.map(\.calls) == [4, 6, 0])
        #expect(ActivityBottomPanel.pickSeries("provider:Anthropic", history: history)?.map(\.calls) == [4, 6, 0])
        #expect(ActivityBottomPanel.pickSeries("place:cloud", history: history)?.map(\.pages) == [0, 4, 0])
        #expect(ActivityBottomPanel.pickSeries("tab:runs", history: history) == nil, "a tab draws its own graph")
        #expect(ActivityBottomPanel.pickFigures("place:cloud", history: history) == "4 pages · 11 calls in the last hour")
    }

    @Test("two projects' series are one, by key, minute by minute added")
    func seriesMerged() {
        let merged = ActivityBottomPanel.mergedSeries(
            [.init(key: "a", pages: [1, 2]), .init(key: "b", pages: [0, 1])], [.init(key: "a", pages: [3, 0, 1])]
        )
        #expect(merged.map(\.key) == ["a", "b"])
        #expect(merged[0].pages == [4, 2, 1])
    }
}
