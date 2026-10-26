//
//  ActivityPopoverUpNextTests.swift
//  FicheroTests
//
//  activity.popover.now-plus-next (#5960): the popover says one grey line for each of the first three UP NEXT items.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
struct ActivityPopoverUpNextTests {
    @Test("the first three UP NEXT items, in the engine's order, with what each waits for")
    func firstThree() throws {
        let json = """
        {"live": [], "background": [], "history": 0, "up_next": [
          {"id": "a", "name": "Run a", "stage": "Describe", "after": "Read", "why": "after Read"},
          {"id": "b", "name": "Run b", "why": "Waiting: the model lane"},
          {"id": "c", "name": "Run c", "why": "in the queue"},
          {"id": "d", "name": "Run d", "why": "in the queue"}]}
        """
        let summary = try JSONDecoder().decode(Components.Schemas.ActivitySummary.self, from: Data(json.utf8))
        let lines = ActivityPopoverSummary(jobs: [], paused: false, activity: summary).upNext
        #expect(lines.map(\.id) == ["a", "b", "c"])
        #expect(lines[0].waiting == "after Read", "the engine's why, as sent")
        #expect(lines[1].waiting == "Waiting: the model lane")
        #expect(lines[2].waiting == "in the queue")
    }

    @Test("a live block's subtitle is the engine's model and where, as sent; neither: none (activity.summary.where-and-model)")
    func subtitle() throws {
        let json = """
        {"live": [{"id": "r", "state": "running", "model": "Kraken", "where": "on this Mac"},
                  {"id": "s", "state": "running", "where": "in the cloud"},
                  {"id": "t", "state": "running"}], "background": [], "history": 0}
        """
        let summary = try JSONDecoder().decode(Components.Schemas.ActivitySummary.self, from: Data(json.utf8))
        let blocks = ActivityPopoverSummary(jobs: [], paused: false, activity: summary).blocks
        #expect(blocks.map(\.subtitle) == ["Kraken · on this Mac", "in the cloud", nil])
    }

    @Test("the window lists the engine's UP NEXT items that are not rows, in order, each with its run (two runs tell apart)")
    func windowLines() throws {
        let json = """
        {"live": [], "background": [], "history": 0, "up_next": [
          {"id": "row", "name": "A queued run", "why": "in the queue"},
          {"id": "run-a:2", "name": "Describe", "stage": "Describe", "after": "Read", "why": "after Read", "run_id": "run-a"},
          {"id": "run-b:2", "name": "Describe", "stage": "Describe", "after": "Read", "why": "after Read", "run_id": "run-b"}]}
        """
        let summary = try JSONDecoder().decode(Components.Schemas.ActivitySummary.self, from: Data(json.utf8))
        let names = ["run-a": "Mosquera box", "run-b": "Marshall Diaries · Letters"]
        let lines = ActivityPopoverSummary.upNextLines([summary], excluding: ["row"], runName: { names[$0] })
        #expect(lines.map(\.id) == ["run-a:2", "run-b:2"])
        #expect(lines.map(\.title) == ["Describe · Mosquera box", "Describe · Marshall Diaries · Letters"])
        #expect(lines.first?.waiting == "after Read")
        #expect(ActivityPopoverSummary.upNextLines([summary], excluding: []).count == 3)
        #expect(ActivityPopoverSummary.upNextLines([summary], excluding: []).last?.title == "Describe", "no run known: the stage alone")
    }
}
