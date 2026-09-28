import FicheroAPIClient
import Foundation
import Observation

/// SegmentService using the generated OpenAPI client (source-model App slice A,
/// #4954). A plain transport wrapper, shaped like `EntityService`/
/// `ArtifactService.getArtifact` — exhaustive switch on the typed response,
/// map to an app model, no hand-rolled URL. Holds NO cache: `SegmentStore` is
/// the single owner (`source.app.one-segment-store`) and the only caller of
/// this service.
@MainActor
@Observable
final class SegmentService {
    // internal (not private), matching `EntityService.client`: a future
    // `SegmentService+*.swift` concern extension can reach it directly.
    let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    /// The segments (and their passes) of one source page, whether they
    /// still live in today's `Artifact.ocr_geometry` blocks or, once slice 3
    /// lands, real `Segment` records — the caller cannot tell which
    /// (`source.seam.read-either-store`).
    func listDocumentSegments(
        documentId: String,
        artifactId: String? = nil,
        passId: String? = nil,
        kind: String? = nil
    ) async throws -> (passes: [SegmentPassValue], segments: [Segment]) {
        let response = try await client.api.listDocumentSegmentsApiSegmentsDocumentDocIdGet(
            path: .init(docId: documentId),
            query: .init(artifactId: artifactId, passId: passId, kind: kind)
        )

        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return (
                passes: body.passes.map { SegmentPassValue(generated: $0) },
                segments: body.segments.map { Segment(generated: $0) }
            )
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SegmentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }

    /// ONE segment as it is now, resolved through forwarding (merge, split, or
    /// deleted-then-restored) when the id is no longer live
    /// (`source.segment.forwarding`).
    ///
    /// Added for `source.app.segment-events-patch-in-place`: a change event names
    /// the segments that changed, and replacing exactly those rows needs a
    /// per-segment read. Re-reading the whole document instead is the wholesale
    /// reload that behaviour exists to forbid.
    ///
    /// Returns nil for 422 — the id named something this build cannot resolve
    /// (a provisional id, or a row that is gone with no forwarding trail). A
    /// missing row is not an error the caller can act on: the store drops that
    /// segment rather than holding a stale copy.
    func segment(id: String) async throws -> Segment? {
        let response = try await client.api.getSegmentApiSegmentsSegmentIdGet(
            path: .init(segmentId: id)
        )

        switch response {
        case .ok(let okResponse):
            return Segment(generated: try okResponse.body.json.segment)
        case .unprocessableContent:
            return nil
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }
}

extension SegmentService {
    /// Each segment's RESOLVED direction on one page, from the page text's blocks (#5199): what the
    /// on-image labels lay out in. Empty when the page has no text of its own.
    func lineDirections(documentId: String) async throws -> [String: String] {
        let response = try await client.api.getDocumentTextApiSegmentsDocumentDocumentIdTextGet(
            path: .init(documentId: documentId)
        )
        guard case .ok(let okResponse) = response else { return [:] }
        return SegmentLabel.directions(from: try okResponse.body.json)
    }

    /// Every reading of one segment and which counts per kind, WITH its basis (the Inspector's Text
    /// section). Nil for 422: an id this build cannot resolve has no readings to show.
    func readings(segmentId: String) async throws -> InspectorText? {
        let response = try await client.api.listSegmentReadingsApiSegmentsSegmentIdReadingsGet(
            path: .init(segmentId: segmentId)
        )
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            let readings = body.items.map {
                InspectorText.Reading(
                    id: $0.id, kind: $0.kind, content: $0.content, maker: $0.provenanceKind.rawValue,
                    author: $0.createdBy, guideline: $0.guideline, pairId: $0.pairId, pairRole: $0.pairRole,
                    correctsId: $0.correctsRepresentationId, level: $0.level,
                    machineConfidence: $0.machineConfidence, readFromRenditionId: $0.readFromRenditionId
                )
            }
            let counting = body.counting.additionalProperties.mapValues {
                InspectorText.Counting(readingId: $0.representationId, why: .init(basis: $0.basis?.rawValue))
            }
            return InspectorText(
                readings: readings,
                retracted: Set(body.items.filter { $0.retracted == true }.map(\.id)),
                counting: counting
            )
        case .unprocessableContent:
            return nil
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }
}

extension SegmentService {
    /// The file an imported pass was read from, exactly as it arrived (#5149, the Making section's
    /// Show Original). Nil for 404 -- a pass not made from a kept file.
    func original(passId: String) async throws -> PassOriginal? {
        let response = try await client.api.getPassOriginalApiSegmentsPassesPassIdOriginalGet(
            path: .init(passId: passId)
        )
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            guard let bytes = Data(base64Encoded: body.contentBase64) else {
                throw SegmentServiceError.serverError("the original's bytes did not decode")
            }
            return PassOriginal(
                fileName: body.fileName, importFormat: body.importFormat, mediaType: body.mediaType, bytes: bytes
            )
        case .undocumented(404, _):
            return nil
        case .unprocessableContent:
            return nil
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }
}

extension SegmentService {
    /// The language, script, direction and encoding the engine resolves for ONE segment, each with
    /// where it came from (#5158; `GET /api/source-settings/resolve`). Empty for an id it cannot find.
    func resolvedSettings(segmentId: String) async throws -> [InspectorLanguage.Setting] {
        try await resolvedSettings(query: .init(segmentId: segmentId))
    }

    /// The same for a source -- a folder, document or page -- with no segment (the Inspector's Direction row).
    func resolvedSettings(documentId: String) async throws -> [InspectorLanguage.Setting] {
        try await resolvedSettings(query: .init(documentId: documentId))
    }

    private func resolvedSettings(
        query: Operations.ResolveSourceSettingsApiSourceSettingsResolveGet.Input.Query
    ) async throws -> [InspectorLanguage.Setting] {
        let response = try await client.api.resolveSourceSettingsApiSourceSettingsResolveGet(query: query)
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.settings.map {
                InspectorLanguage.Setting(
                    key: $0.key, value: $0.value, status: $0.status, source: $0.source, basis: $0.basis, level: $0.level
                )
            }
        case .undocumented(404, _), .unprocessableContent:
            return []
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }
}

/// A kept original: its bytes as they arrived, and what to call it.
struct PassOriginal: Equatable {
    let fileName: String?
    let importFormat: String?
    let mediaType: String
    let bytes: Data

    /// For reading on screen: UTF-8 when it is, else Latin-1 (which decodes any byte), so a file in
    /// another encoding is still shown rather than refused.
    var text: String {
        String(data: bytes, encoding: .utf8) ?? String(data: bytes, encoding: .isoLatin1) ?? ""
    }
}

enum SegmentServiceError: Error, LocalizedError {
    case unexpectedResponse(Int)
    case serverError(String)

    var errorDescription: String? {
        switch self {
        case .unexpectedResponse(let code):
            return "Unexpected response from segment service (status: \(code))"
        case .serverError(let message):
            return "Server error: \(message)"
        }
    }
}
