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
        filePath: String? = nil,
        documentId: String? = nil,
        pageId: String? = nil,
        displayName: String? = nil,
        sequence: Int? = nil
    ) -> WorkflowStreamEvent {
        .fileComplete(
            threadId: "thread-1",
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
}
