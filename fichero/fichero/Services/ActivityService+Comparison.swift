import FicheroAPIClient
import Foundation

// MARK: - GET /api/workflow-execution/comparisons (#4341)
//
// Diff two runs of the same input. Comparing two runs that ALREADY exist
// costs nothing; what costs is producing a second run to compare against,
// which is what `cost_notice` is about. That string is passed through
// verbatim — the client never composes its own version of it.

extension ActivityService {

    /// Compare two completed runs by thread id.
    func compareRuns(left: String, right: String) async throws -> RunComparison {
        let response = try await client.api
            .compareWorkflowRunsApiWorkflowExecutionComparisonsGet(
                query: .init(left: left, right: right),
            )

        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return Self.comparison(from: body)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(
                detail?.detail?.description ?? "Validation error"
            )
        case .undocumented(let statusCode, _):
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

    nonisolated static func comparison(
        from response: Components.Schemas.RunComparisonResponse
    ) -> RunComparison {
        RunComparison(
            left: side(from: response.left),
            right: side(from: response.right),
            comparable: response.comparable,
            incomparableReason: response.incomparableReason,
            sameInput: response.sameInput,
            inputNote: response.inputNote ?? "",
            identical: response.identical,
            differenceCount: response.differenceCount ?? 0,
            compared: (response.compared ?? []).map(artifactComparison(from:)),
            onlyLeft: (response.onlyLeft ?? []).map(orphan(from:)),
            onlyRight: (response.onlyRight ?? []).map(orphan(from:)),
            costNotice: response.costNotice ?? ""
        )
    }

    nonisolated static func side(
        from side: Components.Schemas.ComparisonSideResponse
    ) -> RunComparisonSide {
        RunComparisonSide(
            threadId: side.threadId,
            workflowId: side.workflowId,
            workflowName: side.workflowName,
            status: side.status,
            error: side.error,
            durationMs: side.durationMs,
            artifactCount: side.artifactCount ?? 0,
            stepsTotal: side.stepsTotal ?? 0,
            stepsFailed: side.stepsFailed ?? 0,
            stepsNotRun: side.stepsNotRun ?? 0,
            stepsProducedNothing: side.stepsProducedNothing ?? 0,
            resolvedDocumentCount: side.resolvedDocumentCount
        )
    }

    nonisolated static func artifactComparison(
        from item: Components.Schemas.ArtifactComparisonResponse
    ) -> RunArtifactComparison {
        RunArtifactComparison(
            documentId: item.documentId,
            documentName: item.documentName,
            artifactType: item.artifactType,
            identical: item.identical,
            leftProvenance: provenanceText(item.left),
            rightProvenance: provenanceText(item.right),
            textDifferences: (item.textDiff?.differences ?? []).map(textDifference(from:)),
            textDifferencesTruncated: item.textDiff?.differencesTruncated ?? false,
            textDifferenceCount: item.textDiff?.differenceCount ?? 0,
            setDifferences: (item.setDifferences ?? []).map(setDifference(from:)),
            valueDifferences: (item.valueDifferences ?? []).map {
                RunValueDifference(fieldName: $0.fieldName, left: $0.left, right: $0.right)
            }
        )
    }

    nonisolated static func textDifference(
        from diff: Components.Schemas.TextDifferenceResponse
    ) -> RunTextDifference {
        RunTextDifference(
            kind: diff.kind,
            leftStartLine: diff.leftStartLine,
            rightStartLine: diff.rightStartLine,
            leftLines: diff.leftLines ?? [],
            rightLines: diff.rightLines ?? [],
            leftLineCount: diff.leftLineCount ?? 0,
            rightLineCount: diff.rightLineCount ?? 0,
            linesTruncated: diff.linesTruncated ?? false
        )
    }

    nonisolated static func setDifference(
        from diff: Components.Schemas.SetDifferenceResponse
    ) -> RunSetDifference {
        RunSetDifference(
            fieldName: diff.fieldName,
            onlyLeft: diff.onlyLeft ?? [],
            onlyRight: diff.onlyRight ?? [],
            sharedCount: diff.sharedCount ?? 0,
            onlyLeftCount: diff.onlyLeftCount ?? 0,
            onlyRightCount: diff.onlyRightCount ?? 0,
            labelsTruncated: diff.labelsTruncated ?? false
        )
    }

    nonisolated static func orphan(
        from ref: Components.Schemas.ComparisonArtifactRefResponse
    ) -> RunComparisonOrphan {
        RunComparisonOrphan(
            artifactId: ref.artifactId,
            documentId: ref.documentId,
            documentName: ref.documentName,
            artifactType: ref.artifactType ?? "",
            stepName: ref.stepName,
            provenance: provenanceText(ref)
        )
    }

    /// "anthropic · claude-sonnet-4-6", or nil when neither was recorded —
    /// the same rule the run trace uses, so provenance reads identically
    /// wherever it appears.
    nonisolated static func provenanceText(
        _ ref: Components.Schemas.ComparisonArtifactRefResponse
    ) -> String? {
        let parts = [ref.provider, ref.model].compactMap { value -> String? in
            guard let value, !value.isEmpty else { return nil }
            return value
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}
