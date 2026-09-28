import FicheroAPIClient
import Foundation

/// What is said about a segment (`source.statement.on-segment`, `both-ways`), through the generated
/// client: `GET /api/segments/{id}/statements`. Read-only.
@MainActor
struct StatementService {
    let client: FicheroClient

    func statements(segmentId: String) async throws -> InspectorStatements.Answer {
        let response = try await client.api.segmentStatementsApiSegmentsSegmentIdStatementsGet(
            path: .init(segmentId: segmentId)
        )
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return InspectorStatements.Answer(
                claims: body.claims.map {
                    InspectorStatements.Claim(
                        id: $0.claimId, text: $0.text, curationState: $0.curationState, confidence: $0.confidence,
                        via: $0.via, excerpt: $0.excerpt
                    )
                },
                mentions: body.mentions.map {
                    InspectorStatements.Mention(id: $0.entityId, name: $0.name, entityType: $0.entityType, excerpt: $0.excerpt)
                }
            )
        case .unprocessableContent:
            return InspectorStatements.Answer()
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }
}
