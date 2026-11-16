@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `activity.summary.one-row-per-run-in-list` (#5960): the engine lists a live recipe run once, as a live block. The window's rows
/// still cover it: each live block that names a recipe is a row, once, and a run the list still names is not doubled.
struct ActivityLiveRunRowsTests {
    private func block(_ id: String, recipe: String? = "Mosquera", state: String = "running") throws -> Components.Schemas.LiveBlock {
        let name = recipe.map { #""\#($0)""# } ?? "null"
        let json = #"{"id":"\#(id)","recipe":\#(name),"state":"\#(state)","done":7,"failed":1,"left":12,"total":20,"stages":[]}"#
        return try JSONDecoder().decode(Components.Schemas.LiveBlock.self, from: Data(json.utf8))
    }

    @Test("a live recipe run is a row the window lists, with its stage's pages as its bar")
    func liveRunIsARow() throws {
        let rows = ActivityJob.withLiveRuns([], live: [try block("r1")])
        #expect(rows.map(\.id) == ["r1"])
        #expect(rows[0].taskType == ActivityJob.recipeRunKind && rows[0].name == "Mosquera")
        #expect(rows[0].state == .running && rows[0].current == 7 && rows[0].total == 20 && rows[0].percent == 35)
    }

    @Test("a waiting or paused run is a row too, with what it waits for")
    func waitingRun() throws {
        let rows = ActivityJob.withLiveRuns([], live: [try block("r1", state: "paused")])
        #expect(rows[0].state == .paused)
    }

    @Test("a run the list already names is not added twice; a workflow block outside a recipe is left to the list")
    func noDoubles() throws {
        let listed = ActivityJob(id: "r1", taskType: ActivityJob.recipeRunKind, name: "Mosquera")
        let rows = ActivityJob.withLiveRuns([listed], live: [try block("r1"), try block("w9", recipe: nil)])
        #expect(rows.map(\.id) == ["r1"])
    }

    @Test("live rows come first, before the queue and history")
    func order() throws {
        let history = ActivityJob(id: "h1", taskType: "x", name: "Old", state: .completed, isEarlier: true)
        #expect(ActivityJob.withLiveRuns([history], live: [try block("r1")]).map(\.id) == ["r1", "h1"])
    }
}
