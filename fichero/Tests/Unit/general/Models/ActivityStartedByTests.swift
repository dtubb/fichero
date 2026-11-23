@testable import Fichero
import Testing

/// `activity.window.started-by` (#5354): a row says who or what started it, in words.
struct ActivityStartedByTests {
    @Test("a person, the recipe, a schedule, a trigger and an assistant each read as themselves")
    func words() {
        #expect(ActivityDetails.startedByWords("Daniel") == "Started by Daniel")
        #expect(ActivityDetails.startedByWords("automatic") == "Started automatically")
        #expect(ActivityDetails.startedByWords("schedule:nightly") == "Started by a schedule")
        #expect(ActivityDetails.startedByWords("trigger:new-image") == "Started by a trigger")
        #expect(ActivityDetails.startedByWords("Claude Code for Daniel") == "Started by Claude Code for Daniel")
        #expect(ActivityDetails.startedByWords("read-again:r1") == "Started to read failed pages again")
    }

    @Test("a run's own rows and an empty value say nothing")
    func silent() {
        #expect(ActivityDetails.startedByWords("workflow") == nil)
        #expect(ActivityDetails.startedByWords("") == nil)
        #expect(ActivityDetails.startedByWords(nil) == nil)
    }
}

/// `activity.window.started-by` (#5354), the window's table row: its Started By cell says it in the same words as the opened run.
struct ActivityStartedByRowTests {
    @Test("the table row's cell words who or what started it, and says nothing for a run's own row")
    func cell() {
        var row = ActivityPaneFixture.row("r", .running)
        row.startedBy = "schedule:nightly"
        #expect(ActivityPane.startedByLine(row) == "Started by a schedule")
        row.startedBy = "automatic"
        #expect(ActivityPane.startedByLine(row) == "Started automatically")
        row.startedBy = "workflow"
        #expect(ActivityPane.startedByLine(row) == "")
        row.startedBy = nil
        #expect(ActivityPane.startedByLine(row) == "")
    }
}
