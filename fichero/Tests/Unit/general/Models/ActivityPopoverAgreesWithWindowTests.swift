//
//  ActivityPopoverAgreesWithWindowTests.swift
//  FicheroTests
//
//  #5852 (owner, 2026-10-19): the toolbar popover and the Activity window read ONE engine summary (the popover draws it). The popover shows the
//  live "Recipe › Stage › Workflow" with "7 of 20 pages · folders", one line per background kind, and a wait that
//  looks waiting and says why. Spec: `activity.popover.same-summary`. The summary is decoded from the engine's JSON, as
//  the app receives it.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
struct ActivityPopoverAgreesWithWindowTests {
    private func summary() throws -> Components.Schemas.ActivitySummary {
        let json = """
        {"live": [{"id": "rec", "recipe": "Run the recipe: Transcribe", "stage": "Reading the lines with Kraken",
                   "workflow": "Read lines", "state": "running", "done": 7, "failed": 1, "left": 12, "total": 20,
                   "folders_done": 2, "folders_total": 8}],
         "background": [{"kind": "embed", "name": "Embed for search", "state": "waiting",
                         "reason": "Waiting for reading to finish", "done": 0, "total": 40},
                        {"kind": "thumbnail", "name": "Thumbnails", "state": "running", "done": 5, "total": 9}],
         "history": 3}
        """
        return try JSONDecoder().decode(Components.Schemas.ActivitySummary.self, from: Data(json.utf8))
    }

    @Test func thePopoverSaysWhatIsWorkingAndWhatItActsOn() throws {
        let popover = ActivityPopoverSummary(jobs: [], paused: false, activity: try summary())
        let block = try #require(popover.blocks.first)
        #expect(block.title == "Run the recipe: Transcribe › Reading the lines with Kraken › Read lines")
        #expect(block.counts == "7 of 20 pages · 2 of 8 folders · 1 failed")
        #expect(block.waiting == nil)
    }

    @Test func backgroundWorkIsOneLinePerKindAndAWaitLooksWaitingAndSaysWhy() throws {
        let popover = ActivityPopoverSummary(jobs: [], paused: false, activity: try summary())
        #expect(popover.background.map(\.text) == ["Embed for search · 0 of 40", "Thumbnails · 5 of 9"])
        #expect(popover.background[0].waiting == "Waiting for reading to finish")
        #expect(popover.background[1].waiting == nil)
    }

    @Test func noSummaryMeansNoBlocks() {
        let popover = ActivityPopoverSummary(jobs: [], paused: false)
        #expect(popover.blocks.isEmpty && popover.background.isEmpty)
    }

    @Test func oneOfOneReadsAsASingularPageAndFolder() throws {
        let json = """
        {"live": [{"id": "r", "recipe": "R", "stage": "S", "workflow": "W", "state": "running", "done": 1,
                   "failed": 0, "left": 0, "total": 1, "folders_done": 1, "folders_total": 1}],
         "background": [], "history": 0}
        """
        let one = try JSONDecoder().decode(Components.Schemas.ActivitySummary.self, from: Data(json.utf8))
        let block = try #require(ActivityPopoverSummary(jobs: [], paused: false, activity: one).blocks.first)
        #expect(block.counts == "1 of 1 page · 1 of 1 folder")
    }

    @Test func aRunningJobOfAKindTheSummaryHasALineForIsNotSaidTwice() throws {
        let jobs = [ActivityJob(id: "t", taskType: "thumbnail", name: "Thumbnails", current: 5, total: 9, state: .running),
                    ActivityJob(id: "x", taskType: "other", name: "Something else", current: 1, total: 2, state: .running)]
        let popover = ActivityPopoverSummary(jobs: jobs, paused: false, activity: try summary())
        #expect(popover.running.map(\.name) == ["Something else"])
        #expect(popover.background.map(\.id).contains("thumbnail"))
    }
}
