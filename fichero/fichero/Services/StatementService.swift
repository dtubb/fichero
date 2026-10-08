import FicheroAPIClient
import Foundation

/// What is said about a segment (`source.statement.on-segment`, `both-ways`), through the generated
/// client: `GET /api/segments/{id}/statements`; and its corrections from the line
/// (`source.extract.corrected-in-place`, #5602): a name re-pointed (`mention.repoint`) or its words fixed
/// (`mention.respan`), a statement dated (`claim.patch`) or rejected (`claim.transition`) -- each one
/// audited action in the engine.
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
                    InspectorStatements.Mention(
                        id: $0.entityId, name: $0.name, entityType: $0.entityType, excerpt: $0.excerpt,
                        sourceCharStart: $0.sourceCharStart, sourceCharEnd: $0.sourceCharEnd,
                        charStart: $0.charStart, charEnd: $0.charEnd,
                        correctedByPerson: $0.correctedByPerson ?? false
                    )
                }
            )
        case .unprocessableContent:
            return InspectorStatements.Answer()
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }

    /// "Not this person": the name at this mark is `toEntityId`.
    func repoint(
        _ mention: InspectorStatements.Mention, documentId: String, toEntityId: String
    ) async throws {
        guard let span = mention.pageSpan else { throw SegmentServiceError.serverError("This mark has no place in the page text") }
        let response = try await client.api.repointMentionApiEntitiesEntityIdMentionsRepointPost(
            path: .init(entityId: mention.id),
            body: .json(.init(documentId: documentId, charStart: span.start, charEnd: span.end, toEntityId: toEntityId))
        )
        switch response {
        case .ok: return
        case .unprocessableContent(let error):
            throw SegmentServiceError.serverError((try? error.body.json)?.detail?.description ?? "The mark was refused")
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }

    /// "Fix the words": the mention is `newStart`..`newEnd` of the page text.
    func respan(
        _ mention: InspectorStatements.Mention, documentId: String, newStart: Int, newEnd: Int
    ) async throws {
        guard let span = mention.pageSpan else { throw SegmentServiceError.serverError("This mark has no place in the page text") }
        let response = try await client.api.respanMentionApiEntitiesEntityIdMentionsRespanPost(
            path: .init(entityId: mention.id),
            body: .json(.init(
                documentId: documentId, charStart: span.start, charEnd: span.end,
                newCharStart: newStart, newCharEnd: newEnd
            ))
        )
        switch response {
        case .ok: return
        case .unprocessableContent(let error):
            throw SegmentServiceError.serverError((try? error.body.json)?.detail?.description ?? "The words were refused")
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }

    /// "Change date": the statement's date (`time_start`).
    func setDate(claimId: String, date: String) async throws {
        var body = Components.Schemas.ClaimPatchRequest()
        body.timeStart = date
        let response = try await client.api.patchClaimApiClaimsClaimIdPatch(
            path: .init(claimId: claimId), body: .json(body)
        )
        switch response {
        case .ok: return
        case .unprocessableContent(let error):
            throw SegmentServiceError.serverError((try? error.body.json)?.detail?.description ?? "The date was refused")
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }

    /// "Not true": the statement is rejected by a person.
    func reject(claimId: String) async throws {
        let response = try await client.api.transitionClaimApiClaimsClaimIdTransitionPatch(
            path: .init(claimId: claimId),
            body: .json(.init(toState: "rejected", reviewedBy: "human"))
        )
        switch response {
        case .ok: return
        case .unprocessableContent(let error):
            throw SegmentServiceError.serverError((try? error.body.json)?.detail?.description ?? "The rejection was refused")
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }
}
