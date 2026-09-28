import FicheroAPIClient
import Foundation

/// What rights apply to a target, worked out by the engine from the library down (`source.rights.*`),
/// through the generated client. Reads only: records are set and withdrawn by audited actions.
@MainActor
struct RightsService {
    let client: FicheroClient

    /// `targetKind` is "segment", "document" or "library".
    func effective(targetKind: String, targetId: String) async throws -> InspectorRights.Answer {
        guard let kind = Components.Schemas.RightsTarget(rawValue: targetKind) else {
            throw SegmentServiceError.unexpectedResponse(422)
        }
        let response = try await client.api.getEffectiveRightsApiRightsEffectiveGet(
            query: .init(targetKind: kind, targetId: targetId)
        )
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            let records = body.records.filter { $0.withdrawnAt == nil }.compactMap { record in
                record.id.map {
                    InspectorRights.Record(
                        id: $0, targetKind: record.targetKind, targetId: record.targetId,
                        holders: record.holders ?? [], conditions: record.conditions, labels: record.labels ?? [],
                        restricted: record.restricted ?? false, readers: record.readers ?? [],
                        modelUse: record.modelUse, createdBy: record.createdBy
                    )
                }
            }
            return InspectorRights.Answer(
                restricted: body.restricted, readers: body.readers, modelUse: body.modelUse, labels: body.labels,
                records: records
            )
        case .unprocessableContent:
            return InspectorRights.Answer()
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }
}
