import FicheroAPIClient
import Foundation

extension SegmentService {
    /// The types the Type menu and the Inspector's Type row offer for this page, in the engine's order.
    func regionTypes(documentId: String) async throws -> [RegionTypeChoice] {
        let response = try await client.api.listRegionTypesApiSegmentsDocumentDocIdTypesGet(path: .init(docId: documentId))
        switch response {
        case .ok(let answer):
            return try answer.body.json.types.map {
                RegionTypeChoice(label: $0.label, zone: $0.zone, subtype: $0.subtype, onPage: $0.onPage)
            }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SegmentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }
}
