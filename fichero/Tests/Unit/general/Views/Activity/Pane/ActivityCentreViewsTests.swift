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

    @Test("Runs and Recipes offer all three views; Cost offers Table and Graph")
    func offered() {
        #expect(ActivityCentreView.offered(for: .runs) == [.table, .graph, .visual])
        #expect(ActivityCentreView.offered(for: .recipes) == [.table, .graph, .visual])
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

    @Test("Recipes' Visual draws each recipe's newest run as its steps in order, each with its counts")
    func runGraph() {
        func line(_ id: String, _ level: ActivityRecipeLine.Level, _ name: String, done: Int = 0, failed: Int = 0,
                  model: String? = nil, children: [ActivityRecipeLine]? = nil) -> ActivityRecipeLine {
            ActivityRecipeLine(id: id, level: level, name: name, model: model, pagesDone: done, pagesFailed: failed,
                               secondsPerPage: 4, children: children)
        }
        let newest = line("run:2", .run, "Done", children: [
            line("s1", .step, "Detect Segments", done: 20, model: "kraken:blla"),
            line("s2", .step, "Read Lines", done: 17, failed: 3, model: "kraken:catmus")
        ])
        let older = line("run:1", .run, "Failed", children: [line("s0", .step, "Detect Segments")])
        let empty = line("recipe:b", .recipe, "No steps yet", children: [line("run:3", .run, "Done", children: [])])
        let runs = ActivityRunGraph.newestRuns([line("recipe:a", .recipe, "Letters", children: [newest, older]), empty])

        #expect(runs.map(\.id) == ["run:2"], "the newest run only; a run with no steps is not drawn")
        #expect(runs[0].recipe == "Letters")
        #expect(runs[0].nodes.map(\.name) == ["Detect Segments", "Read Lines"])
        #expect(runs[0].nodes.map(\.tone) == [.done, .failed])
        #expect(runs[0].nodes[1].perPage == "4 s")
    }
}
