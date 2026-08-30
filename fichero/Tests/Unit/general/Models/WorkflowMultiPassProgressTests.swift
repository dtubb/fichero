@testable import Fichero
import Foundation
import Testing

struct WorkflowMultiPassProgressTests {
    @Test("multi-pass completion counts each document once")
    func multiPassCompletionCountsUniqueDocuments() {
        var execution = WorkflowExecution(
            id: "workflow",
            name: "Transcribe HTR",
            threadId: "thread",
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

        execution.apply(completion(nodeId: "draft"))
        execution.apply(completion(nodeId: "review"))

        #expect(execution.processedFiles == 1)
        #expect(execution.overallProgress == 1)
    }

    private func completion(nodeId: String) -> WorkflowStreamEvent {
        .fileComplete(
            threadId: "thread",
            nodeId: nodeId,
            filePath: "/scan.pdf",
            fileIndex: 0,
            fileTotal: 1,
            progress: 1,
            cached: false,
            documentId: "document",
            pageId: "page",
            displayName: "Page 1",
            sequence: 1
        )
    }
}
