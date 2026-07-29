//
//  ActivityServiceTests.swift
//  FicheroTests
//
//  Response-mapping coverage for the generated OpenAPI Activity client (#2413 #2392).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import Testing

@Suite("ActivityService response mapping")
@MainActor
struct ActivityServiceTests {

    private let service = ActivityService(ficheroClient: FicheroClient(libraryPath: nil))

    @Test("convertToActivityItem preserves declared fields and coerces metadata to strings")
    func activityItemMapping() throws {
        let metadata = Components.Schemas.ActivityResponse.MetadataPayload(
            additionalProperties: try OpenAPIObjectContainer(unvalidatedValue: [
                "count": 42,
                "ready": true,
                "label": "step-1"
            ])
        )
        let response = Components.Schemas.ActivityResponse(
            id: "act-1",
            _type: "node_started",
            level: "info",
            timestamp: "2024-01-01T12:00:00Z",
            message: "started",
            workflowId: "wf-1",
            batchId: "batch-1",
            threadId: "thread-1",
            nodeId: "node-1",
            metadata: metadata,
            durationMs: 123.4,
            error: nil
        )

        let item = service.convertToActivityItem(response)

        #expect(item.id == "act-1")
        #expect(item.type == "node_started")
        #expect(item.level == "info")
        #expect(item.message == "started")
        #expect(item.workflowId == "wf-1")
        #expect(item.batchId == "batch-1")
        #expect(item.threadId == "thread-1")
        #expect(item.nodeId == "node-1")
        #expect(item.durationMs == 123.4)
        #expect(item.metadataStrings?["count"] == "42")
        #expect(item.metadataStrings?["ready"] == "true")
        #expect(item.metadataStrings?["label"] == "step-1")
    }

    @Test("convertToActivityStats unwraps typed additionalProperties maps")
    func activityStatsMapping() {
        let response = Components.Schemas.ActivityStatsResponse(
            totalActivities: 10,
            activitiesByType: .init(additionalProperties: ["workflow_started": 3, "node_completed": 7]),
            activitiesByLevel: .init(additionalProperties: ["info": 8, "error": 2]),
            errorCount: 2,
            warningCount: 1,
            avgWorkflowDurationMs: 456.7,
            successRate: 0.8,
            periodStart: "2024-01-01T00:00:00Z",
            periodEnd: "2024-01-02T00:00:00Z"
        )

        let stats = service.convertToActivityStats(response)

        #expect(stats.totalActivities == 10)
        #expect(stats.activitiesByType == ["workflow_started": 3, "node_completed": 7])
        #expect(stats.activitiesByLevel == ["info": 8, "error": 2])
        #expect(stats.errorCount == 2)
        #expect(stats.warningCount == 1)
        #expect(stats.avgWorkflowDurationMs == 456.7)
        #expect(stats.successRate == 0.8)
        #expect(stats.periodStart == "2024-01-01T00:00:00Z")
        #expect(stats.periodEnd == "2024-01-02T00:00:00Z")
    }

    @Test("convertToCheckpointHistory passes threadId through and unwraps dynamic values")
    func checkpointHistoryMapping() throws {
        let response = Components.Schemas.CheckpointHistoryResponse(
            threadId: "ignored-thread",
            workflowId: "wf-2",
            workflowName: "Transcribe",
            totalSteps: 2,
            checkpoints: [
                Components.Schemas.CheckpointSnapshot(
                    checkpointId: "cp-1",
                    parentCheckpointId: "cp-0",
                    step: 1,
                    timestamp: "2024-01-01T12:00:00Z",
                    nodeName: "ocr",
                    stateValues: .init(additionalProperties: try OpenAPIObjectContainer(unvalidatedValue: ["page": "1"])),
                    writes: .init(additionalProperties: try OpenAPIObjectContainer(unvalidatedValue: ["text": "hello"])),
                    nextNodes: ["extract"]
                )
            ]
        )

        let history = service.convertToCheckpointHistory(response, threadId: "thread-override")

        // The response's own threadId is authoritative; convertToCheckpointHistory
        // deliberately ignores the passed-in threadId parameter.
        #expect(history.threadId == "ignored-thread")
        #expect(history.workflowId == "wf-2")
        #expect(history.workflowName == "Transcribe")
        #expect(history.totalSteps == 2)
        #expect(history.checkpoints.count == 1)
        #expect(history.checkpoints[0].checkpointId == "cp-1")
        #expect(history.checkpoints[0].step == 1)
        #expect(history.checkpoints[0].stateValues["page"]?.value as? String == "1")
        #expect(history.checkpoints[0].writes["text"]?.value as? String == "hello")
        #expect(history.checkpoints[0].nextNodes == ["extract"])
    }

    @Test("convertToWorkflowRun unwraps snapshot, node map and timeline")
    func workflowRunMapping() throws {
        let response = Components.Schemas.WorkflowRunResponse(
            threadId: "thread-3",
            workflowId: "wf-3",
            workflowName: "Summarize",
            pythonCode: "print('ok')",
            executionLog: "log line",
            status: "completed",
            startedAt: "2024-01-01T12:00:00Z",
            completedAt: "2024-01-01T12:01:00Z",
            durationMs: 1234.0,
            error: nil,
            workflowSnapshot: .init(additionalProperties: try OpenAPIObjectContainer(unvalidatedValue: ["key": "value"])),
            nodeNameMap: .init(additionalProperties: ["n1": "Extract"]),
            progressTimeline: .init(additionalProperties: try OpenAPIObjectContainer(unvalidatedValue: ["t": 1])),
            diagramMermaid: "graph TD; A-->B"
        )

        let run = service.convertToWorkflowRun(response)

        #expect(run.threadId == "thread-3")
        #expect(run.workflowId == "wf-3")
        #expect(run.workflowName == "Summarize")
        #expect(run.pythonCode == "print('ok')")
        #expect(run.executionLog == "log line")
        #expect(run.status == "completed")
        #expect(run.durationMs == 1234.0)
        #expect(run.workflowSnapshot?["key"] as? String == "value")
        #expect(run.nodeNameMap == ["n1": "Extract"])
        #expect(run.progressTimeline?["t"] as? Int == 1)
        #expect(run.diagramMermaid == "graph TD; A-->B")
    }
}
