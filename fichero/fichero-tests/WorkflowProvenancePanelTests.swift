//
//  WorkflowProvenancePanelTests.swift
//  FicheroTests
//
//  Tests for WorkflowProvenancePanel sort + identity helpers (#2434).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

// MARK: - Sort

@Suite("WorkflowProvenancePanel.sortNewestFirst")
struct WorkflowProvenanceSortTests {

    private func run(
        workflowId: String,
        startedAt: String?,
        completedAt: String? = nil
    ) -> Components.Schemas.WorkflowRunProvenanceResponse {
        Components.Schemas.WorkflowRunProvenanceResponse(
            threadId: nil,
            batchId: nil,
            itemIndex: nil,
            workflowId: workflowId,
            workflowName: workflowId,
            provider: nil,
            model: nil,
            result: nil,
            startedAt: startedAt,
            completedAt: completedAt
        )
    }

    @Test("empty input returns empty")
    func emptyInput() {
        let result = WorkflowProvenancePanel.sortNewestFirst([])
        #expect(result.isEmpty)
    }

    @Test("single run returns unchanged")
    func singleRun() {
        let runs = [run(workflowId: "wf-1", startedAt: "2024-01-01T00:00:00Z")]
        let result = WorkflowProvenancePanel.sortNewestFirst(runs)
        #expect(result.count == 1)
        #expect(result[0].workflowId == "wf-1")
    }

    @Test("newest startedAt appears first")
    func newestFirst() {
        let runs = [
            run(workflowId: "older", startedAt: "2024-01-01T00:00:00Z"),
            run(workflowId: "newest", startedAt: "2024-06-01T00:00:00Z"),
            run(workflowId: "middle", startedAt: "2024-03-01T00:00:00Z")
        ]
        let sorted = WorkflowProvenancePanel.sortNewestFirst(runs)
        #expect(sorted[0].workflowId == "newest")
        #expect(sorted[1].workflowId == "middle")
        #expect(sorted[2].workflowId == "older")
    }

    @Test("run with nil startedAt falls to end")
    func nilStartedAtFallsToEnd() {
        let runs = [
            run(workflowId: "no-date", startedAt: nil),
            run(workflowId: "dated", startedAt: "2024-01-01T00:00:00Z")
        ]
        let sorted = WorkflowProvenancePanel.sortNewestFirst(runs)
        #expect(sorted[0].workflowId == "dated")
        #expect(sorted[1].workflowId == "no-date")
    }

    @Test("same workflow run twice — both appear, newest first")
    func duplicateWorkflowId() {
        let runs = [
            run(workflowId: "wf-transcribe", startedAt: "2024-01-01T00:00:00Z"),
            run(workflowId: "wf-transcribe", startedAt: "2024-06-01T00:00:00Z")
        ]
        let sorted = WorkflowProvenancePanel.sortNewestFirst(runs)
        #expect(sorted.count == 2)
        #expect(sorted[0].startedAt == "2024-06-01T00:00:00Z")
        #expect(sorted[1].startedAt == "2024-01-01T00:00:00Z")
    }
}

@Suite("WorkflowProvenancePanel error handling")
struct WorkflowProvenanceErrorHandlingTests {
    @Test("404 missing history maps to empty state instead of raw error")
    func notFoundBecomesEmptyState() {
        let error = EntityService.ServiceError.unexpectedResponse(404)
        #expect(WorkflowProvenancePanel.loadErrorMessage(for: error) == nil)
    }

    @Test("non-404 responses still surface an error")
    func otherResponsesStillSurfaceError() {
        let error = EntityService.ServiceError.unexpectedResponse(500)
        #expect(WorkflowProvenancePanel.loadErrorMessage(for: error) == error.localizedDescription)
    }
}
