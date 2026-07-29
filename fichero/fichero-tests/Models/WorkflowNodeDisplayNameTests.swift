@testable import Fichero
import Foundation
import Testing

struct WorkflowNodeDisplayNameTests {
    @Test("node begin retains the backend display name")
    func nodeBeginRetainsDisplayName() {
        var execution = WorkflowExecution(
            id: "workflow",
            name: "Transcribe",
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

        execution.apply(.nodeBegin(
            threadId: "thread",
            nodeId: "transcribe-review-medium",
            nodeName: "Review Pass"
        ))

        #expect(execution.nodeStates["transcribe-review-medium"]?.displayName == "Review Pass")
    }
}
