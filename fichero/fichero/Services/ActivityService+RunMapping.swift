import FicheroAPIClient
import Foundation

// MARK: - Generated run payload → app types (#4284)
//
// Split out of `ActivityService` so that file stays inside the 400-line
// limit. Everything here is a pure shape translation: no network, no
// decisions about what a status MEANS. Interpretation belongs to
// `RunTraceModelBuilder`, which is unit-testable without a client.

extension ActivityService {

    /// Convert generated workflow run to app type.
    func convertToWorkflowRun(_ response: Components.Schemas.WorkflowRunResponse) -> WorkflowRunResponse {
        // Extract workflow snapshot from OpenAPI Payload wrapper
        let workflowSnapshot: [String: Any]? = response.workflowSnapshot?.additionalProperties.value as? [String: Any]

        // Extract node name map from OpenAPI Payload wrapper
        let nodeNameMap: [String: String]? = response.nodeNameMap?.additionalProperties

        // Extract progress timeline from OpenAPI Payload wrapper
        let progressTimeline: [String: Any]? = response.progressTimeline?.additionalProperties.value as? [String: Any]

        return WorkflowRunResponse(
            threadId: response.threadId,
            workflowId: response.workflowId,
            workflowName: response.workflowName,
            pythonCode: response.pythonCode,
            executionLog: response.executionLog,
            status: response.status.rawValue,
            startedAt: response.startedAt,
            completedAt: response.completedAt,
            durationMs: response.durationMs,
            error: response.error,
            workflowSnapshot: workflowSnapshot,
            nodeNameMap: nodeNameMap,
            progressTimeline: progressTimeline,
            diagramMermaid: response.diagramMermaid,
            runArtifacts: (response.runArtifacts ?? []).map(Self.runArtifact(from:)),
            steps: (response.steps ?? []).map(Self.runStep(from:))
        )
    }

    /// One planned step and what it produced. `producedNothing` is carried
    /// through as the server stated it — never recomputed from
    /// `artifacts.isEmpty`, which cannot tell "ran and produced nothing"
    /// apart from "never ran".
    nonisolated static func runStep(
        from step: Components.Schemas.WorkflowRunStepResponse
    ) -> WorkflowRunStep {
        WorkflowRunStep(
            nodeId: step.nodeId,
            nodeName: step.nodeName,
            tool: step.tool,
            status: step.status,
            startedAt: step.startedAt,
            completedAt: step.completedAt,
            durationMs: step.durationMs,
            error: step.error,
            skipReason: step.skipReason,
            terminatedByRun: step.terminatedByRun,
            filesTotal: step.filesTotal,
            filesSucceeded: step.filesSucceeded,
            filesFailed: step.filesFailed,
            artifactCount: step.artifactCount,
            producedNothing: step.producedNothing,
            artifacts: (step.artifacts ?? []).map(Self.runArtifact(from:))
        )
    }

    /// One artifact with its full provenance chain and preview state. The
    /// preview fields are passed through verbatim: `contentTruncated` is the
    /// server's statement that what is in `contentPreview` is NOT the whole
    /// content, and nothing here may soften that.
    nonisolated static func runArtifact(
        from artifact: Components.Schemas.WorkflowRunArtifactResponse
    ) -> WorkflowRunArtifact {
        WorkflowRunArtifact(
            artifactId: artifact.artifactId,
            artifactType: artifact.artifactType,
            documentId: artifact.documentId,
            documentName: artifact.documentName,
            sourceDocumentId: artifact.sourceDocumentId,
            sourceDocumentName: artifact.sourceDocumentName,
            runId: artifact.runId,
            stepName: artifact.stepName,
            nodeName: artifact.nodeName,
            sequence: artifact.sequence,
            createdAt: artifact.createdAt,
            provider: artifact.provider,
            model: artifact.model,
            contentChars: artifact.contentChars,
            contentPreview: artifact.contentPreview,
            contentTruncated: artifact.contentTruncated,
            hasStructuredData: artifact.hasStructuredData
        )
    }
}
