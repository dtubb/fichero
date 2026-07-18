@testable import Fichero
import Foundation
import Testing

@Suite("BatchProgress and CreateBatchRequest")
struct BatchProgressTests {

    @Test("BatchProgress decodes the backend's snake-case progress payload")
    func batchProgressDecoding() throws {
        let data = Data(
            """
            {"batch_id":"batch-1","total_items":10,"completed_items":4,"failed_items":1,
             "running_items":2,"pending_items":3,"progress_percent":40.0,
             "estimated_remaining_seconds":12.5,"avg_item_duration_seconds":2.4}
            """.utf8
        )

        let progress = try JSONDecoder().decode(BatchProgress.self, from: data)

        #expect(progress.batchId == "batch-1")
        #expect(progress.completedItems == 4)
        #expect(progress.failedItems == 1)
        #expect(progress.runningItems == 2)
        #expect(progress.pendingItems == 3)
        #expect(progress.progressPercent == 40)
        #expect(progress.estimatedRemainingSeconds == 12.5)
        #expect(progress.avgItemDurationSeconds == 2.4)
    }

    @Test("CreateBatchRequest encodes workflow and concurrency using API field names")
    func createBatchRequestEncoding() throws {
        let request = CreateBatchRequest(
            workflowId: "workflow-1",
            items: [BatchInputItem(inputs: ["selected_doc_ids": "doc-1"])],
            maxConcurrent: 3
        )

        let json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any])
        #expect(json["workflow_id"] as? String == "workflow-1")
        #expect(json["max_concurrent"] as? Int == 3)
        let items = try #require(json["items"] as? [[String: [String: String]]])
        #expect(items == [["inputs": ["selected_doc_ids": "doc-1"]]])
    }
}
