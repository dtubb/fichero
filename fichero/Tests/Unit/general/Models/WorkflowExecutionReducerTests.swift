//
//  WorkflowExecutionReducerTests.swift
//  FicheroTests
//
//  Tests for `WorkflowExecution.apply(_:)` — the shared SSE event reducer used by
//  both `WorkflowExecutionObserver` (editor) and `WorkflowExecutionStore`
//  (Activity monitor, #2546).
//
//  Regression for the #2546 follow-up: the live graph-parallel run path
//  (enable_parallel=True) emits file_start/file_complete/file_error but NEVER
//  `parallel_start`, so `totalFiles` was never set and the Activity "Overall
//  Progress" bar sat at 0% for a running workflow. The reducer now seeds
//  `totalFiles` from the `file_total` carried on file events, so
//  `overallProgress` drives 0 → 1.0 as files complete.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct WorkflowExecutionReducerTests {

    // MARK: - Helpers

    private func runningExecution() -> WorkflowExecution {
        WorkflowExecution(
            id: "wf-1",
            name: "Transcribe HTR",
            threadId: "thread-1",
            startTime: Date(),
            status: .running,
            nodeStates: [:],
            documentProgress: [:],
            currentFilePath: nil,
            currentNodeId: nil,
            currentNodeName: nil,
            isRunning: true,
            workflowError: nil
        )
    }

    private func fileStart(
        _ index: Int,
        total: Int,
        filePath: String? = nil,
        documentId: String? = nil,
        pageId: String? = nil,
        displayName: String? = nil,
        sequence: Int? = nil
    ) -> WorkflowStreamEvent {
        .fileStart(
            threadId: "thread-1",
            nodeId: "node-1",
            filePath: filePath ?? "/docs/page-\(index).pdf",
            fileIndex: index,
            fileTotal: total,
            progress: Double(index) / Double(total),
            documentId: documentId,
            pageId: pageId,
            displayName: displayName,
            sequence: sequence
        )
    }

    private func fileComplete(
        _ index: Int,
        total: Int,
        threadId: String = "thread-1",
        filePath: String? = nil,
        documentId: String? = nil,
        pageId: String? = nil,
        displayName: String? = nil,
        sequence: Int? = nil
    ) -> WorkflowStreamEvent {
        .fileComplete(
            threadId: threadId,
            nodeId: "node-1",
            filePath: filePath ?? "/docs/page-\(index).pdf",
            fileIndex: index,
            fileTotal: total,
            progress: Double(index + 1) / Double(total),
            cached: false,
            documentId: documentId,
            pageId: pageId,
            displayName: displayName,
            sequence: sequence
        )
    }

    // MARK: - Tests

    @Test("file events seed totalFiles so overallProgress climbs 0 → 1.0")
    func fileEventsDriveOverallProgress() {
        var execution = runningExecution()

        // Before any events: no files known, no nodes → 0%.
        #expect(execution.overallProgress == 0)

        // First file starts: totalFiles is now known, none processed yet → 0%.
        execution.apply(fileStart(0, total: 3))
        #expect(execution.totalFiles == 3)
        #expect(execution.processedFiles == 0)
        #expect(execution.overallProgress == 0)

        // Files complete one by one — the bar moves off 0%.
        execution.apply(fileComplete(0, total: 3))
        #expect(execution.processedFiles == 1)
        #expect(execution.overallProgress == 1.0 / 3.0)

        execution.apply(fileComplete(1, total: 3))
        #expect(execution.overallProgress == 2.0 / 3.0)

        execution.apply(fileComplete(2, total: 3))
        #expect(execution.processedFiles == 3)
        #expect(execution.overallProgress == 1.0)
    }

    @Test("a cached file_complete with no preceding file_start still seeds totalFiles")
    func cachedFileCompleteSeedsTotal() {
        var execution = runningExecution()

        // #700 cache hit emits file_complete directly (no file_start).
        execution.apply(fileComplete(0, total: 2))
        #expect(execution.totalFiles == 2)
        #expect(execution.processedFiles == 1)
        #expect(execution.overallProgress == 0.5)
    }

    @Test("file_error counts toward processed and the bar still completes")
    func fileErrorCountsAsProcessed() {
        var execution = runningExecution()

        execution.apply(fileStart(0, total: 2))
        execution.apply(fileComplete(0, total: 2))
        execution.apply(
            .fileError(
                threadId: "thread-1",
                nodeId: "node-1",
                filePath: "/docs/page-1.pdf",
                error: "boom",
                progress: 1.0,
                documentId: nil,
                pageId: nil,
                displayName: nil,
                sequence: nil
            )
        )

        #expect(execution.totalFiles == 2)
        #expect(execution.processedFiles == 2)
        #expect(execution.overallProgress == 1.0)
    }

    @Test("overallProgress is nil once the run is no longer running")
    func overallProgressNilWhenFinished() {
        var execution = runningExecution()
        execution.apply(fileStart(0, total: 1))
        execution.apply(fileComplete(0, total: 1))
        execution.apply(.complete(threadId: "thread-1", checkpointId: nil, finalState: nil))

        #expect(execution.isRunning == false)
        #expect(execution.overallProgress == nil)
    }

    @Test("cancelled event is terminal AND renders as cancelled, not failed (#4321)")
    func cancelledEventIsTerminal() {
        var execution = runningExecution()

        execution.apply(.cancelled(threadId: "thread-1"))

        #expect(execution.status == .cancelled)
        #expect(execution.isRunning == false)
        #expect(execution.workflowError == "Cancelled by user")
    }

    @Test("duplicate parent paths stay distinct when page ids differ")
    func duplicateParentPathsUseStablePageIdentity() {
        var execution = runningExecution()
        let sharedPath = "/docs/scan.pdf"

        execution.apply(
            fileStart(
                0,
                total: 2,
                filePath: sharedPath,
                documentId: "pdf-1",
                pageId: "page-1",
                displayName: "Page 1",
                sequence: 1
            )
        )
        execution.apply(
            fileStart(
                1,
                total: 2,
                filePath: sharedPath,
                documentId: "pdf-1",
                pageId: "page-2",
                displayName: "Page 2",
                sequence: 2
            )
        )
        execution.apply(
            fileComplete(
                0,
                total: 2,
                filePath: sharedPath,
                documentId: "pdf-1",
                pageId: "page-1",
                displayName: "Page 1",
                sequence: 1
            )
        )

        #expect(execution.documentProgress.count == 2)
        #expect(execution.documentProgress["page-1"]?.documentName == "Page 1")
        #expect(execution.documentProgress["page-2"]?.documentName == "Page 2")
        if case .completed? = execution.documentProgress["page-1"]?.stepStatuses["node-1"] {
            // expected
        } else {
            Issue.record("Expected page-1 to be completed")
        }
        if case .running? = execution.documentProgress["page-2"]?.stepStatuses["node-1"] {
            // expected
        } else {
            Issue.record("Expected page-2 to remain running")
        }
    }

    @Test("observer keeps same-workflow concurrent runs distinct by threadId")
    func observerSeparatesConcurrentRunsByThreadId() {
        let observer = WorkflowExecutionObserver()

        observer.startExecution(
            workflowId: "wf-1",
            name: "Transcribe",
            threadId: "thread-1"
        )
        observer.startExecution(
            workflowId: "wf-1",
            name: "Transcribe",
            threadId: "thread-2"
        )

        observer.handleEvent(fileComplete(0, total: 1, threadId: "thread-1"), forThreadId: "thread-1")
        observer.handleEvent(
            fileComplete(
                0,
                total: 1,
                threadId: "thread-2",
                filePath: "/docs/other.pdf",
                displayName: "Other"
            ),
            forThreadId: "thread-2"
        )

        #expect(observer.activeExecutions.count == 2)
        #expect(observer.activeExecutions["thread-1"]?.threadId == "thread-1")
        #expect(observer.activeExecutions["thread-2"]?.threadId == "thread-2")
        #expect(observer.activeExecutions["thread-1"]?.documentProgress.count == 1)
        #expect(observer.activeExecutions["thread-2"]?.documentProgress.count == 1)
    }

    @Test("promoting a provisional execution preserves early events")
    func provisionalExecutionPromotionKeepsEarlyEvents() {
        let observer = WorkflowExecutionObserver()
        let provisionalThreadId = "pending:test"

        observer.startExecution(
            workflowId: "wf-1",
            name: "Transcribe",
            threadId: provisionalThreadId
        )
        observer.handleEvent(
            fileStart(
                0,
                total: 1,
                filePath: "/docs/scan.pdf",
                documentId: "pdf-1",
                pageId: "page-1",
                displayName: "Page 1",
                sequence: 1
            ),
            forThreadId: provisionalThreadId
        )

        observer.promoteExecution(from: provisionalThreadId, to: "thread-1")
        observer.handleEvent(
            fileComplete(
                0,
                total: 1,
                threadId: "thread-1",
                filePath: "/docs/scan.pdf",
                documentId: "pdf-1",
                pageId: "page-1",
                displayName: "Page 1",
                sequence: 1
            ),
            forThreadId: "thread-1"
        )

        #expect(observer.activeExecutions[provisionalThreadId] == nil)
        #expect(observer.activeExecutions["thread-1"]?.threadId == "thread-1")
        #expect(observer.activeExecutions["thread-1"]?.documentProgress["page-1"]?.documentName == "Page 1")
        if case .completed? = observer.activeExecutions["thread-1"]?.documentProgress["page-1"]?.stepStatuses["node-1"] {
            // expected
        } else {
            Issue.record("Expected promoted execution to keep early file state")
        }
    }

}

@MainActor
struct ActivityStatusMappingTests {

    @Test("activity maps paused executions explicitly")
    func activityMapsPausedExecutionsExplicitly() {
        #expect(activityMapExecutionStatus(.paused) == .paused)
        #expect(activityMapExecutionStatus(.running) == .running)
        #expect(activityMapExecutionStatus(.completed) == .completed)
    }

    @Test("activity resolves live and persisted terminal statuses")
    func activityResolvesRunStatuses() {
        let selectedRun = SelectedActivityRun(
            id: "thread-1",
            name: "Transcribe",
            workflowId: "wf-1",
            threadId: "thread-1",
            timestamp: Date(),
            status: .running,
            isLive: true,
            childType: nil
        )

        let pausedExecution = WorkflowExecution(
            id: "wf-1",
            name: "Transcribe",
            threadId: "thread-1",
            startTime: Date(),
            status: .paused,
            nodeStates: [:],
            documentProgress: [:],
            currentFilePath: nil,
            currentNodeId: nil,
            currentNodeName: nil,
            isRunning: false,
            workflowError: nil
        )
        #expect(
            ActivityViewHelpers.selectedRunStatus(
                selectedRun: selectedRun,
                liveExecution: pausedExecution,
                persistedRun: nil
            ) == .paused
        )

        let cancelledRun = WorkflowRunResponse(
            threadId: "thread-1",
            workflowId: "wf-1",
            workflowName: "Transcribe",
            pythonCode: nil,
            executionLog: nil,
            status: "cancelled",
            startedAt: nil,
            completedAt: nil,
            durationMs: nil,
            error: nil
        )
        #expect(
            ActivityViewHelpers.selectedRunStatus(
                selectedRun: selectedRun,
                liveExecution: nil,
                persistedRun: cancelledRun
            ) == .cancelled
        )
    }
}
