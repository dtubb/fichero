@testable import Fichero
import Foundation
import Testing

struct ActivityMonitorParallelNodeTests {
    @Test("parallel nodes show only their own files")
    func parallelNodesFilterFilesByStepIdentity() throws {
        var draft = NodeExecutionState(nodeId: "draft")
        draft.status = .parallelRunning
        draft.fileTotal = 1
        var review = NodeExecutionState(nodeId: "review")
        review.status = .parallelRunning
        review.fileTotal = 1
        let execution = WorkflowExecution(
            id: "workflow",
            name: "Transcribe Ensemble",
            threadId: "thread",
            startTime: Date(),
            status: .running,
            nodeStates: ["draft": draft, "review": review],
            documentProgress: [
                "page-1": DocumentProgress(
                    id: "page-1",
                    documentName: "Page 1",
                    stepStatuses: ["draft": .running]
                ),
                "page-2": DocumentProgress(
                    id: "page-2",
                    documentName: "Page 2",
                    stepStatuses: ["review": .running]
                )
            ],
            currentFilePath: nil,
            currentNodeId: nil,
            currentNodeName: nil,
            isRunning: true,
            workflowError: nil
        )

        let run = try #require(ActivityMonitorRow.rows(from: [execution]).first)
        let nodes = try #require(run.children)

        #expect(nodes.first { $0.id.hasSuffix(":draft") }?.children?.map(\.name) == ["Page 1"])
        #expect(nodes.first { $0.id.hasSuffix(":review") }?.children?.map(\.name) == ["Page 2"])
    }
}
