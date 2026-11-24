import FicheroAPIClient
import Foundation

/// A type a region can be set to (`source.editor.region-type-is-seen-and-set`): the engine's label with its SegmOnto
/// zone, and whether the page already carries it. The engine owns the list; the app only draws it.
struct RegionTypeChoice: Equatable, Identifiable {
    let label: String
    let zone: String?
    let subtype: String?
    let onPage: Bool
    var id: String { label }

    /// "MainZone · head": the zone a label means, for a menu's help text; nil for a label the page brought.
    var zoneName: String? {
        guard let zone else { return nil }
        return subtype.map { "\(zone) · \($0)" } ?? zone
    }
}

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
