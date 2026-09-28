import FicheroAPIClient
import Foundation

/// The project's declared signs, one sign's uses, and a segment's letterform (`source.sign.*`,
/// `source.letterform.*`), through the generated client. Reads only.
@MainActor
struct SignService {
    let client: FicheroClient

    /// The project's sign list, withdrawn signs left out.
    func signs() async throws -> [InspectorSigns.Sign] {
        let response = try await client.api.listSignsApiSignsGet()
        switch response {
        case .ok(let okResponse):
            // A row without an id (the schema lets it be absent) could not be named; it is not shown.
            return try okResponse.body.json.items.filter { $0.deletedAt == nil }.compactMap { sign in
                sign.id.map {
                    InspectorSigns.Sign(
                        id: $0, name: sign.name, pictureSegmentId: sign.pictureSegmentId, codePoint: sign.codePoint,
                        listReferences: (sign.listReferences ?? []).compactMap(Self.listReference),
                        variantOf: sign.variantOf, variant: sign.variant
                    )
                }
            }
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }

    /// How many times the project uses one sign, across every live reading.
    func totalUses(signId: String) async throws -> Int {
        let response = try await client.api.listSignInstancesApiSignsSignIdInstancesGet(path: .init(signId: signId))
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.total
        case .unprocessableContent:
            return 0
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Every use of one sign that this reader may read, and how many were left out (#5180) -- what
    /// "Every Instance" gathers in the Segments pane (#4942).
    func instances(signId: String) async throws -> (uses: [SegmentsGathered.SignUse], withheld: Int) {
        let response = try await client.api.listSignInstancesApiSignsSignIdInstancesGet(path: .init(signId: signId))
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            let uses = body.items.map {
                SegmentsGathered.SignUse(
                    representationId: $0.representationId, segmentId: $0.segmentId, documentId: $0.documentId, count: $0.count
                )
            }
            return (uses, body.withheld ?? 0)
        case .unprocessableContent:
            return ([], 0)
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }

    /// The live description of one mark, and the project's allographs by id, to name it.
    func letterforms(segmentId: String) async throws -> [InspectorSigns.Letterform] {
        let response = try await client.api.descriptionOfSegmentApiLetterformsSegmentSegmentIdGet(
            path: .init(segmentId: segmentId)
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items.filter { $0.withdrawnAt == nil }.compactMap { form in
                form.id.map {
                    InspectorSigns.Letterform(
                        id: $0, character: form.character, allographId: form.allographId, handId: form.handId,
                        features: (form.features ?? []).map { (component: $0.component, feature: $0.feature) },
                        describedBy: form.createdBy
                    )
                }
            }
        case .unprocessableContent:
            return []
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }

    func allographNames() async throws -> [String: String] {
        let response = try await client.api.listAllographsApiLetterformsAllographsGet()
        switch response {
        case .ok(let okResponse):
            let pairs = try okResponse.body.json.items.compactMap { item in item.id.map { ($0, item.name) } }
            return Dictionary(pairs, uniquingKeysWith: { first, _ in first })
        case .unprocessableContent:
            return [:]
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }

    /// One `{authority, number}` from the sign's open list of list references.
    private static func listReference(
        _ item: Components.Schemas.DeclaredSign.ListReferencesPayloadPayload
    ) -> InspectorSigns.ListReference? {
        let fields = item.additionalProperties.value
        guard let authority = fields["authority"] as? String else { return nil }
        let number = fields["number"] as? String ?? (fields["number"] as? Int).map(String.init) ?? ""
        return InspectorSigns.ListReference(authority: authority, number: number)
    }
}
