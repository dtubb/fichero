@testable import Fichero
import Foundation
import Testing

/// `activity.pane.names-what-it-works-on` (#6588; spec docs/contributor_manual/specs/ui/activity-pane.md): an import's
/// row names the project and the count, its children are the stages it holds with their own counts, and under the
/// running stage the files it is on now, by name.
struct ActivityNamesWhatItWorksOnTests {
    @Test("an import's row holds its stages, and the running stage the files in flight by name")
    func importRow() throws {
        var job = ActivityJob(id: "derivatives", taskType: "derivatives", name: "Prepare pages · Letters · 2,618",
                              current: 11, total: 2618, state: .running)
        job.stages = [
            .init(title: "Thumbnails", state: "done", done: 2618, total: 2618),
            .init(title: "Text", state: "running", done: 11, total: 2618,
                  inFlight: ["letter-012.jpg", "letter-013.jpg"]),
            .init(title: "Embed for search", state: "waiting", done: 0, total: 2618)
        ]
        let row = ActivityMonitorRow.job(job, libraryId: nil, projectName: "Letters")

        #expect(row.name == "Prepare pages · Letters · 2,618")
        let stages = try #require(row.children)
        #expect(stages.map(\.name) == ["Thumbnails", "Text", "Embed for search"])
        #expect(stages.map(\.done) == [2618, 11, 0])
        #expect(stages[1].children?.map(\.name) == ["letter-012.jpg", "letter-013.jpg"])
        #expect(stages[0].children == nil && stages[2].children == nil, "only the files in flight are named")
    }

    @Test("a job that is not an import keeps its trail and no stage children")
    func otherJobs() {
        var job = ActivityJob(id: "recipe-1", taskType: "run-a-recipe", name: "Run the recipe", state: .running)
        job.stages = [.init(title: "Read", state: "running", done: 1, total: 4)]
        #expect(ActivityMonitorRow.job(job, libraryId: nil, projectName: nil).children == nil)
    }
}
