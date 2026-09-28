import FicheroAPIClient
import Foundation

/// The project's hands and a segment's attributions (#5161; `source.hand.*`), through the generated
/// client. Reads only: every write is an audited action (`hand.create`, `hand.attribute`,
/// `hand.unattribute`) sent through `ActionsService.invokeAction` by `AuditedAction`.
@MainActor
struct HandService {
    let client: FicheroClient

    /// Every hand in the project, withdrawn ones left out.
    func hands() async throws -> [InspectorHands.ListedHand] {
        let response = try await client.api.listHandsApiHandsGet()
        switch response {
        case .ok(let okResponse):
            // The schema lets `id` be absent (the engine fills it by default); a row without one
            // could not be attributed to, so it is not offered.
            return try okResponse.body.json.items.filter { $0.deletedAt == nil }.compactMap { hand in
                hand.id.map {
                    InspectorHands.ListedHand(id: $0, label: hand.label, scribe: hand.scribe, date: hand.date, style: hand.style)
                }
            }
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Every live attribution of one segment: which hand, how sure, who judged it, and whether the
    /// FILE said so (an imported `<handShift>`).
    func attributions(segmentId: String) async throws -> [InspectorHands.Attribution] {
        let response = try await client.api.handsOfSegmentApiHandsSegmentSegmentIdGet(path: .init(segmentId: segmentId))
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items.filter { $0.withdrawnAt == nil }.compactMap { attribution in
                attribution.id.map {
                    InspectorHands.Attribution(
                        id: $0, handId: attribution.handId, certainty: attribution.certainty,
                        judgedBy: attribution.createdBy, fromFile: attribution.source
                    )
                }
            }
        case .unprocessableContent:
            return []
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }
}
