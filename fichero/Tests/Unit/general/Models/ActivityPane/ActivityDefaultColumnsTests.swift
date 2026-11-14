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

    @Test("cost: spent and the estimate while running, spent once ended, blank for local work, Free at $0, Not priced")
    func cost() {
        var running = ActivityPaneFixture.row("r", .running, costUsd: 0.42)
        running.costEstimateUsd = 1.1
        #expect(ActivityPane.costLine(running) == "$0.42 · ~$1.10 more")
        var ended = running
        ended.phase = .done
        #expect(ActivityPane.costLine(ended) == "$0.42")
        #expect(ActivityPane.costLine(ActivityPaneFixture.row("local", .done)).isEmpty)
        let unpriced = ActivityPaneFixture.row("u", .done, tokens: 10)
        #expect(ActivityPane.costLine(unpriced) == "Not priced")
        #expect(ActivityPane.costLine(ActivityPaneFixture.row("z", .done, costUsd: 0)) == "Free", "a $0 priced call, never $0.00")
    }

    @Test("a time is one short unit: 48 s, 3 min, 2 h; never secs. or a full stop")
    func shortTimes() {
        #expect(ActivityMonitorRow.duration(48) == "48 s")
        #expect(ActivityMonitorRow.duration(170) == "3 min")
        #expect(ActivityMonitorRow.duration(3_570) == "1 h")
        #expect(ActivityMonitorRow.duration(7_300) == "2 h")
        var ended = ActivityPaneFixture.row("t", .done, started: ActivityPaneFixture.day)
        ended.ended = ActivityPaneFixture.day.addingTimeInterval(48)
        #expect(ActivityPane.timeLine(ended) == "48 s")
    }
}
