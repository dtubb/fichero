//
//  ActivityPopoverAgreesWithWindowTests.swift
//  FicheroTests
//
//  #5852 (owner, 2026-10-19): the toolbar popover and the Activity window read ONE engine summary. The popover shows the
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

    @Test func theWindowsLiveSectionReadsTheSameWordsAsThePopoverAcrossProjects() throws {
        let one = try summary()
        let section = ActivityLiveSection(summaries: [one, one])
        let popover = ActivityPopoverSummary(jobs: [], paused: false, activity: one)
        #expect(section.blocks.count == 2 && section.blocks[0] == popover.blocks[0])
        #expect(section.background.map(\.text) == popover.background.map(\.text) + popover.background.map(\.text))
    }
}
