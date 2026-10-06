//
//  ActivityRunMappingTests.swift
//  FicheroTests
//
//  Sidebar test coverage sprint (#583). Covers the previously-untested
//  Activity-run mapping logic: ActivityRunStatus icon/color/workflowStatus
//  and ActivityRun.selection (#5561: a job id and its project). These are the
//  pure value-mappers that feed the Activity sidebar → viewMode navigation;
//  the rest of the sidebar
//  surface is already exercised by DragDropTests / SidebarItemTests /
//  DocumentStoreAndSidebarTypesTests.
//

@testable import Fichero
import Foundation
import SwiftUI
import Testing

// MARK: - ActivityRunStatus

struct ActivityRunStatusMappingTests {

    @Test("workflowStatus maps every case to the app-wide run vocabulary")
    func workflowStatusMapsAllCases() {
        #expect(ActivityRunStatus.running.workflowStatus == .running)
        #expect(ActivityRunStatus.paused.workflowStatus == .paused)
        #expect(ActivityRunStatus.completed.workflowStatus == .completed)
        #expect(ActivityRunStatus.failed.workflowStatus == .failed)
        #expect(ActivityRunStatus.cancelled.workflowStatus == .cancelled)
    }

    @Test("workflow_started maps to running")
    func workflowStartedMapsToRunning() {
        #expect(activityMapActivityType("workflow_started") == .running)
    }

    @MainActor
    @Test("runsByWorkflow surfaces started run and lets terminal event win")
    func runsByWorkflowUsesNewestActivityPerThread() {
        let library = LibraryManager.LibraryReference(
            url: FileManager.default.temporaryDirectory.appendingPathComponent("ActivityRunMappingTests.fichero"),
            document: FicheroDocument(),
            displayName: "Test Library",
            id: UUID(uuidString: "11111111-1111-1111-1111-111111111111")
        )
        let started = ActivityItem(
            id: "started",
            type: "workflow_started",
            level: "info",
            timestamp: "2026-06-25T12:00:00Z",
            message: "Workflow 'Transcribe' started",
            workflowId: "wf-1",
            threadId: "thread-1"
        )
        let completed = ActivityItem(
            id: "completed",
            type: "workflow_completed",
            level: "info",
            timestamp: "2026-06-25T12:00:05Z",
            message: "Workflow 'Transcribe' completed",
            workflowId: "wf-1",
            threadId: "thread-1"
        )

        let groups = runsByWorkflow(
            for: library,
            activeExecutions: [:],
            historicalRuns: [library.id: [started, completed]]
        )
        let runs = groups.values.flatMap { $0 }

        #expect(runs.count == 1)
        #expect(runs.first?.runId == "thread-1")
        #expect(runs.first?.status == .completed)
    }

    @Test("icon is the expected SF Symbol for every case")
    func iconValues() {
        #expect(ActivityRunStatus.running.icon == "play.circle.fill")
        #expect(ActivityRunStatus.completed.icon == "checkmark.circle.fill")
        #expect(ActivityRunStatus.failed.icon == "xmark.circle.fill")
        #expect(ActivityRunStatus.cancelled.icon == "stop.circle.fill")
    }

    @Test("color is the expected accent for every case")
    func colorValues() {
        #expect(ActivityRunStatus.running.color == .blue)
        #expect(ActivityRunStatus.completed.color == .green)
        #expect(ActivityRunStatus.failed.color == .red)
        #expect(ActivityRunStatus.cancelled.color == .orange)
    }

    @Test("every icon is non-empty")
    func iconsNonEmpty() {
        let all: [ActivityRunStatus] = [.running, .completed, .failed, .cancelled]
        for status in all {
            #expect(!status.icon.isEmpty)
        }
    }
}

// MARK: - ActivityRun.selection (#5561)

struct ActivityRunSelectionTests {

    private func makeRun() -> ActivityRun {
        ActivityRun(
            id: "lib-scoped:run-1",
            runId: "thread-42",
            workflowId: "wf-7",
            threadId: "thread-42",
            workflowName: "Transcribe",
            timestamp: Date(timeIntervalSince1970: 1_000),
            status: .running,
            progress: 0.5,
            currentStep: "ocr",
            errorCount: 0,
            fileCount: 3,
            isLive: true,
            libraryId: UUID(uuidString: "11111111-1111-1111-1111-111111111111"),
            libraryName: "Letters"
        )
    }

    @Test("a run's selection is its job (the thread id) and its project, nothing copied")
    func selectionIsTheJobAndItsProject() {
        let selection = makeRun().selection
        #expect(selection.jobId == "thread-42")
        #expect(selection.jobId != "lib-scoped:run-1")
        #expect(selection.libraryId == UUID(uuidString: "11111111-1111-1111-1111-111111111111"))
    }
}
