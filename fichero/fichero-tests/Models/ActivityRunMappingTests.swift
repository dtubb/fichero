//
//  ActivityRunMappingTests.swift
//  FicheroTests
//
//  Sidebar test coverage sprint (#583). Covers the previously-untested
//  Activity-run mapping logic: ActivityRunStatus icon/color/toStatusType,
//  ActivityRun.toSelectedRun field mapping, SelectedActivityRun.with, and
//  ActivityChildType label/icon. These are the pure value-mappers that feed
//  the Activity sidebar → viewMode navigation; the rest of the sidebar
//  surface is already exercised by DragDropTests / SidebarItemTests /
//  DocumentStoreAndSidebarTypesTests.
//

@testable import Fichero
import Foundation
import SwiftUI
import Testing

// MARK: - ActivityRunStatus

struct ActivityRunStatusMappingTests {

    @Test("toStatusType maps every case to its matching ActivityRunStatusType")
    func toStatusTypeMapsAllCases() {
        #expect(ActivityRunStatus.running.toStatusType() == .running)
        #expect(ActivityRunStatus.completed.toStatusType() == .completed)
        #expect(ActivityRunStatus.failed.toStatusType() == .failed)
        #expect(ActivityRunStatus.cancelled.toStatusType() == .cancelled)
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

// MARK: - ActivityRun.toSelectedRun

struct ActivityRunToSelectedRunTests {

    private func makeRun(
        status: ActivityRunStatus = .running,
        isLive: Bool = true
    ) -> ActivityRun {
        ActivityRun(
            id: "lib-scoped:run-1",
            runId: "thread-42",
            workflowId: "wf-7",
            threadId: "thread-42",
            workflowName: "Transcribe",
            timestamp: Date(timeIntervalSince1970: 1_000),
            status: status,
            progress: 0.5,
            currentStep: "ocr",
            errorCount: 0,
            fileCount: 3,
            isLive: isLive,
            libraryId: UUID(uuidString: "11111111-1111-1111-1111-111111111111"),
            libraryName: "Letters"
        )
    }

    @Test("toSelectedRun uses the logical runId as id, not the sidebar id")
    func usesRunIdNotSidebarId() {
        let selected = makeRun().toSelectedRun()
        #expect(selected.id == "thread-42")
        #expect(selected.id != "lib-scoped:run-1")
    }

    @Test("toSelectedRun preserves name / workflowId / threadId / timestamp / isLive")
    func preservesScalarFields() {
        let selected = makeRun(isLive: false).toSelectedRun()
        #expect(selected.name == "Transcribe")
        #expect(selected.workflowId == "wf-7")
        #expect(selected.threadId == "thread-42")
        #expect(selected.timestamp == Date(timeIntervalSince1970: 1_000))
        #expect(selected.isLive == false)
        #expect(selected.libraryId == UUID(uuidString: "11111111-1111-1111-1111-111111111111"))
        #expect(selected.libraryName == "Letters")
    }

    @Test("toSelectedRun converts status via toStatusType")
    func convertsStatus() {
        #expect(makeRun(status: .failed).toSelectedRun().status == .failed)
        #expect(makeRun(status: .cancelled).toSelectedRun().status == .cancelled)
    }

    @Test("toSelectedRun starts with no selected child (overview)")
    func childTypeStartsNil() {
        #expect(makeRun().toSelectedRun().childType == nil)
    }
}

// MARK: - SelectedActivityRun.with

struct SelectedActivityRunWithTests {

    @Test("with(childType:) sets the child and preserves every other field")
    func withSetsChildPreservesRest() {
        let base = SelectedActivityRun(
            id: "thread-42",
            name: "Transcribe",
            workflowId: "wf-7",
            threadId: "thread-42",
            timestamp: Date(timeIntervalSince1970: 1_000),
            status: .completed,
            isLive: false,
            libraryId: UUID(uuidString: "11111111-1111-1111-1111-111111111111"),
            libraryName: "Letters",
            childType: nil
        )
        let withLog = base.with(childType: .log)
        #expect(withLog.childType == .log)
        #expect(withLog.id == base.id)
        #expect(withLog.name == base.name)
        #expect(withLog.workflowId == base.workflowId)
        #expect(withLog.threadId == base.threadId)
        #expect(withLog.timestamp == base.timestamp)
        #expect(withLog.status == base.status)
        #expect(withLog.isLive == base.isLive)
        #expect(withLog.libraryId == base.libraryId)
        #expect(withLog.libraryName == base.libraryName)
    }
}

// MARK: - ActivityChildType

struct ActivityChildTypeMappingTests {

    @Test("label is the expected human-readable string for every case")
    func labels() {
        #expect(ActivityChildType.console.label == "Console")
        #expect(ActivityChildType.progress.label == "Progress")
        #expect(ActivityChildType.log.label == "Log")
    }

    @Test("icon is a non-empty SF Symbol for every case")
    func icons() {
        #expect(ActivityChildType.console.icon == "text.alignleft")
        #expect(ActivityChildType.progress.icon == "chart.bar.fill")
        #expect(ActivityChildType.log.icon == "doc.text")
        for child in ActivityChildType.allCases {
            #expect(!child.icon.isEmpty)
        }
    }
}
