import FicheroAPIClient
import Foundation

/// A segment's typed links (both ways), the library's link types, and a segment's citable reference
/// (`source.link.*`, `source.segment.citable`), through the generated client. Reads only: links are
/// made and withdrawn by audited actions (`typed_link.create`, `typed_link.delete`).
@MainActor
struct LinkService {
    let client: FicheroClient

    /// Every live link touching one thing, read from that end.
    func links(of endId: String) async throws -> [InspectorLinks.Link] {
        let response = try await client.api.linksOfApiLinksOfEndIdGet(path: .init(endId: endId))
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.links.map { link in
                InspectorLinks.Link(
                    id: link.id, linkType: link.linkType, label: link.label, otherKind: link.otherKind,
                    otherId: link.otherId, inbound: link.inbound, certainty: link.certainty, note: link.note
                )
            }
        case .unprocessableContent:
            return []
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }

    /// The link types this library knows, as the Link menu offers them.
    func types() async throws -> [InspectorLinks.LinkType] {
        let response = try await client.api.listLinkTypesApiLinksTypesGet()
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.types.map { InspectorLinks.LinkType(key: $0.key, label: $0.label) }
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }

    /// `fichero:segment/<library>/<page>/<segment>`: worked out by the engine, never stored.
    func reference(segmentId: String) async throws -> String {
        let response = try await client.api.segmentReferenceApiSegmentsSegmentIdReferenceGet(
            path: .init(segmentId: segmentId)
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.reference
        case .unprocessableContent:
            throw SegmentServiceError.unexpectedResponse(404)
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }
}
