//
//  ActivityStepTrailTests.swift
//  FicheroTests
//
//  #6441 `activity.pane.row-says-what-ran-on-what`, `activity.pane.less-is-more-table`, `activity.pane.cost-per-row-and-totals`:
//  the trail, the status bar and the cost cell are one line of text each, built from the engine's counts.
//

@testable import Fichero
import Foundation
import Testing

struct ActivityStepTrailTests {
    private func stage(_ title: String, _ state: String, done: Int = 0, total: Int = 0) -> ActivityJob.Stage {
        ActivityJob.Stage(title: title, state: state, done: done, total: total)
    }

    @Test("the trail reads Import ✓ → Segment ✓ → Read ▶ 34/120 → Names ·")
    func trail() {
        let text = ActivityTrail.text([
            stage("Import", "done"), stage("Segment", "done"), stage("Read", "running", done: 34, total: 120), stage("Names", "waiting")
        ])
        #expect(text == "Import ✓ → Segment ✓ → Read ▶ 34/120 → Names ·")
        #expect(ActivityTrail.text([stage("Read", "failed"), stage("Names", "not run")]) == "Read ✗ → Names –")
        #expect(ActivityTrail.text([]).isEmpty, "a job of its own has no trail")
    }

    @Test("the status bar counts as figures and names the day's spend only when there is one")
    func statusBar() {
        #expect(ActivityTrail.statusBar(running: 3, waiting: 12, spentTodayUsd: 3.2) == "3 running · 12 waiting · $3.20 today")
        #expect(ActivityTrail.statusBar(running: 0, waiting: 0, spentTodayUsd: nil) == "0 running · 0 waiting")
    }

    @Test("the cost cell: spent, the estimate while running, nothing for local work, never $0")
    func cost() {
        #expect(ActivityTrail.cost(spentUsd: 0.42, estimateUsd: 1.1) == "$0.42 · ~$1.10 more")
        #expect(ActivityTrail.cost(spentUsd: 0.42, estimateUsd: nil) == "$0.42")
        #expect(ActivityTrail.cost(spentUsd: nil, estimateUsd: nil).isEmpty)
        #expect(ActivityTrail.cost(spentUsd: 0, estimateUsd: nil).isEmpty, "never $0")
    }

    @Test("an engine row decodes its stages, ran_on, model and cost through the test seam's defaults")
    func jobCarriesTheFacts() {
        var job = ActivityJob(id: "r", taskType: "run-a-recipe", name: "Run the recipe: Letters", state: .running)
        #expect(job.stages.isEmpty && job.ranOn == nil && job.costUsd == nil)
        job.stages = [stage("Read", "running", done: 1, total: 3)]
        job.ranOn = ActivityJob.RanOn(kind: "pages", count: 3, name: nil)
        #expect(ActivityTrail.text(job.stages) == "Read ▶ 1/3")
    }
}
