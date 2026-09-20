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
    ) async throws -> (passes: [SegmentPass], segments: [Segment]) {
        let response = try await client.api.listDocumentSegmentsApiSegmentsDocumentDocIdGet(
            path: .init(docId: documentId),
            query: .init(artifactId: artifactId, passId: passId, kind: kind)
        )

        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return (
                passes: body.passes.map { SegmentPass(generated: $0) },
                segments: body.segments.map { Segment(generated: $0) }
            )
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SegmentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
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
