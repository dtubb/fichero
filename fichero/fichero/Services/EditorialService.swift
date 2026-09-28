import FicheroAPIClient
import Foundation

/// A segment's editorial facts and its reading as the editor prints it (`source.sure.*`), through the
/// generated client. Reads only: every write is an audited action (`editorial.record`,
/// `editorial.withdraw`) sent by `AuditedAction`.
@MainActor
struct EditorialService {
    let client: FicheroClient

    func facts(segmentId: String) async throws -> InspectorEditorial.Answer {
        let response = try await client.api.factsOfSegmentApiEditorialSegmentSegmentIdGet(path: .init(segmentId: segmentId))
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            // The schema lets `id` be absent (the engine fills it by default); a fact without one
            // could not be withdrawn, so it is not listed.
            let facts = body.items.filter { $0.withdrawnAt == nil }.compactMap { fact in
                fact.id.map {
                    InspectorEditorial.Fact(
                        id: $0, kind: fact.kind.rawValue, charStart: fact.charStart, charEnd: fact.charEnd,
                        extent: fact.extent, extentQuantity: fact.extentQuantity, extentUnit: fact.extentUnit,
                        reason: fact.reason, place: fact.place, certainty: fact.certainty,
                        createdBy: fact.createdBy, source: fact.source
                    )
                }
            }
            return InspectorEditorial.Answer(facts: facts, drawn: body.drawn)
        case .unprocessableContent:
            return InspectorEditorial.Answer(facts: [], drawn: nil)
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }
}
