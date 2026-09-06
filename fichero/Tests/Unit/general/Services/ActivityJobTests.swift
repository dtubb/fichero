//
//  ActivityJobTests.swift
//  FicheroTests
//
//  Tests for ActivityJob: the app model both Activity surfaces render from the
//  single `/api/activity/jobs` source. State mapping (especially FAILED, the
//  reason this model exists) and the generated-schema bridge.
//

import FicheroAPIClient
import Foundation
import Testing
@testable import Fichero

struct ActivityJobStateTests {

    @Test("Running / stalled / paused map to themselves")
    func liveStates() {
        #expect(ActivityJob.State(raw: "running") == .running)
        #expect(ActivityJob.State(raw: "stalled") == .stalled)
        #expect(ActivityJob.State(raw: "paused") == .paused)
    }

    @Test("failed and error both fold to .failed")
    func failedAliases() {
        #expect(ActivityJob.State(raw: "failed") == .failed)
        #expect(ActivityJob.State(raw: "error") == .failed)
        #expect(ActivityJob.State(raw: "FAILED") == .failed) // case-insensitive
    }

    @Test("completed aliases fold to .completed")
    func completedAliases() {
        for raw in ["completed", "complete", "done", "finished"] {
            #expect(ActivityJob.State(raw: raw) == .completed, "\(raw) should be .completed")
        }
    }

    @Test("Unknown state is preserved as .other, not swallowed")
    func unknownState() {
        #expect(ActivityJob.State(raw: "queued") == .other("queued"))
    }

    @Test("isFailed is true only for .failed")
    func isFailed() {
        #expect(ActivityJob.State.failed.isFailed)
        #expect(!ActivityJob.State.running.isFailed)
        #expect(!ActivityJob.State.completed.isFailed)
    }

    @Test("isActive is true for running/stalled/paused only")
    func isActive() {
        #expect(ActivityJob.State.running.isActive)
        #expect(ActivityJob.State.stalled.isActive)
        #expect(ActivityJob.State.paused.isActive)
        #expect(!ActivityJob.State.failed.isActive)
        #expect(!ActivityJob.State.completed.isActive)
        #expect(!ActivityJob.State.other("queued").isActive)
    }
}

struct ActivityJobMappingTests {

    @Test("Maps every field from the generated BackgroundJob schema")
    func mapsGeneratedSchema() {
        let generated = Components.Schemas.BackgroundJob(
            id: "job-1",
            taskType: "derivatives",
            name: "Embedding pages",
            library: "Marshall Diaries",
            current: 42,
            total: 100,
            percent: 42.4,
            state: "running"
        )

        let job = ActivityJob(generated)

        #expect(job.id == "job-1")
        #expect(job.taskType == "derivatives")
        #expect(job.name == "Embedding pages")
        #expect(job.library == "Marshall Diaries")
        #expect(job.current == 42)
        #expect(job.total == 100)
        #expect(job.percent == 42.4)
        #expect(job.state == .running)
    }

    @Test("A failed job from the schema surfaces as .failed")
    func failedJobFromSchema() {
        let generated = Components.Schemas.BackgroundJob(
            id: "kraken-1",
            taskType: "workflow",
            name: "Detect Regions (Kraken)",
            current: 0,
            total: 0,
            percent: 0,
            state: "failed",
            reason: "Kraken not installed"
        )
        let job = ActivityJob(generated)
        #expect(job.state == .failed)
        #expect(job.state.isFailed)
        #expect(job.reason == "Kraken not installed")
        #expect(job.taskType == "workflow")
    }

    @Test("A failed workflow job carries its reason through")
    func failedWorkflowReason() {
        let job = ActivityJob(
            id: "kraken-1",
            taskType: "workflow",
            name: "Detect Regions (Kraken)",
            state: .failed,
            reason: "Kraken not installed"
        )
        #expect(job.state.isFailed)
        #expect(job.reason == "Kraken not installed")
        #expect(job.taskType == "workflow")
    }

    @Test("displayPercent rounds; showsProgress needs a known total")
    func progressHelpers() {
        let determinate = ActivityJob(id: "d", name: "x", current: 3, total: 20, percent: 15.6)
        #expect(determinate.displayPercent == 16)
        #expect(determinate.showsProgress)

        let indeterminate = ActivityJob(id: "i", name: "y", current: 0, total: 0, percent: 0)
        #expect(!indeterminate.showsProgress)
    }
}
