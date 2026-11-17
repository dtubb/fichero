@testable import Fichero
import Foundation
import Testing

/// `activity.window.centre-views` (#6588, decisions 38-39; spec docs/contributor_manual/specs/ui/activity-pane.md): the
/// centre's head offers Table, Graph and Visual per sidebar item, the choice kept per item across a relaunch; Visual
/// draws the work as a timeline of bars per lane or per model, coloured by state.
@MainActor
struct ActivityCentreViewsTests {
    private let epoch = Date(timeIntervalSince1970: 1_800_000_000)

    private func row(_ id: String, lane: String?, model: String?, phase: ActivityMonitorRow.Phase, started: Date?,
                     seconds: Double? = nil, children: [ActivityMonitorRow]? = nil) -> ActivityMonitorRow {
        var row = ActivityMonitorRow(
            id: id, kind: .step, libraryId: nil, runRowID: "run", runThreadId: "run", jobId: id, name: id,
            projectName: nil, phase: phase, reason: nil, workingOn: nil, done: 1, total: 1, started: started,
            seconds: seconds, costUsd: nil, tokens: 0, errors: 0, model: model, isLive: false, children: children
        )
        row.lane = lane
        return row
    }

    @Test("Runs offers all three views; Recipes and Cost offer Table and Graph")
    func offered() {
        #expect(ActivityCentreView.offered(for: .runs) == [.table, .graph, .visual])
        #expect(ActivityCentreView.offered(for: .recipes) == [.table, .graph])
        #expect(ActivityCentreView.offered(for: .cost) == [.table, .graph])
    }

    @Test("the choice is kept per item and survives a relaunch; a choice the item does not offer reads Table")
    func remembered() throws {
        var prefs = ActivityPanePrefs()
        prefs.centreViews["runs"] = .visual
        prefs.centreViews["cost"] = .visual
        let reloaded = try JSONDecoder().decode(ActivityPanePrefs.self, from: JSONEncoder().encode(prefs))
        #expect(reloaded.centreView(for: .runs) == .visual)
        #expect(reloaded.centreView(for: .files) == .table, "an item never chosen is Table")
        #expect(reloaded.centreView(for: .cost) == .table, "Cost has no Visual")
    }

    @Test("Visual draws each piece of work from its start to its end on its lane's line, a run by its children")
    func timeline() {
        let now = epoch.addingTimeInterval(600)
        let pages = [
            row("p1", lane: "local-ml", model: "Kraken", phase: .done, started: epoch, seconds: 30),
            row("p2", lane: "network", model: "Claude", phase: .running, started: epoch.addingTimeInterval(60)),
            row("p3", lane: "network", model: "Claude", phase: .waiting, started: nil)
        ]
        let run = row("run", lane: nil, model: nil, phase: .running, started: epoch, children: pages)
        let bars = ActivityTimeline.bars([run], by: .lane, now: now)
        #expect(bars.map(\.id) == ["p1", "p2"], "a run is drawn by its pages; one not started is not drawn")
        #expect(bars[0].line == "local-ml" && bars[0].end == epoch.addingTimeInterval(30))
        #expect(bars[1].end == now, "work still going ends now")
        #expect(ActivityTimeline.bars([run], by: .model, now: now).map(\.line) == ["Kraken", "Claude"])
    }
}
