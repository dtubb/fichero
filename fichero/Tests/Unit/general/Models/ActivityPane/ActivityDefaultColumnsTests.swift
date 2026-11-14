//
//  ActivityDefaultColumnsTests.swift — `activity.pane.default-columns` and `activity.pane.cost-per-row-and-totals` (#6441):
//  the one column table, six on by default, the rest a toggle in the header menu remembered per pane; the cost cell.
//

@testable import Fichero
import SwiftUI
import Testing

struct ActivityDefaultColumnsTests {
    @Test("a fresh pane has the six default columns; Model, Started By, Started and Kind are off")
    func defaults() {
        #expect(ActivityPane.Column.allCases.filter(\.isOnByDefault) == [.source, .name, .state, .trail, .time, .cost])
        #expect(ActivityPane.Column.allCases.filter { !$0.isOnByDefault } == [.model, .startedBy, .started, .kind])
    }

    @Test("the columns a person turns on survive a relaunch, per pane")
    func remembered() throws {
        var columns = TableColumnCustomization<ActivityMonitorRow>()
        columns[visibility: ActivityPane.Column.model.rawValue] = .visible
        let data = ActivityPanePrefs.store(Data(), key: "pane") { $0.columns = columns }
        #expect(ActivityPanePrefs.load(data, key: "pane").columns[visibility: ActivityPane.Column.model.rawValue] == .visible)
    }

    @Test("cost: spent and the estimate while running, spent once ended, blank for local work, Not priced, never $0")
    func cost() {
        var running = ActivityPaneFixture.row("r", .running, costUsd: 0.42)
        running.costEstimateUsd = 1.1
        #expect(ActivityPane.costLine(running) == "$0.42 · ~$1.10 more")
        var ended = running
        ended.phase = .done
        #expect(ActivityPane.costLine(ended) == "$0.42")
        #expect(ActivityPane.costLine(ActivityPaneFixture.row("local", .done)).isEmpty)
        var unpriced = ActivityPaneFixture.row("u", .done)
        unpriced.tokens = 10
        #expect(ActivityPane.costLine(unpriced) == "Not priced")
        #expect(ActivityPane.costLine(ActivityPaneFixture.row("z", .done, costUsd: 0)).isEmpty, "never $0")
    }
}
