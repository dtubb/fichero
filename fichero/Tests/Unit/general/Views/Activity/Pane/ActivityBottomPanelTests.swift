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
}
