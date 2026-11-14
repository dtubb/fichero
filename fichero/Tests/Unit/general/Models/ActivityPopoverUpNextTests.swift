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
}
