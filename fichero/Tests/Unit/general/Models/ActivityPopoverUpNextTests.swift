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

    /// The owner's popover, 2026-11-15: "Update kept export · Letters" twice, once as its background line and once as Up Next;
    /// and "Find regions · 0 of 1" for one-item work (#6599).
    @Test("a waiting job its background line says is not Up Next again, and one-item work has no count")
    func saidOnce() throws {
        let json = """
        {"live": [], "history": 0,
         "background": [{"kind": "kept-export", "name": "Update kept export · Letters", "state": "waiting", "reason": "Waiting a moment",
                         "done": 0, "total": 1},
                        {"kind": "regions", "name": "Find regions", "state": "running", "done": 0, "total": 1}],
         "up_next": [{"id": "k", "name": "Update kept export · Letters", "why": "Waiting a moment"},
                     {"id": "s", "name": "Describe", "run_id": "run", "why": "after Read"}]}
        """
        let summary = try JSONDecoder().decode(Components.Schemas.ActivitySummary.self, from: Data(json.utf8))
        let popover = ActivityPopoverSummary(jobs: [], paused: false, activity: summary)
        #expect(popover.upNext.map(\.id) == ["s"], "a run's stage stays; the kept export is said once")
        #expect(popover.background.map(\.text) == ["Update kept export · Letters", "Find regions"])
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
