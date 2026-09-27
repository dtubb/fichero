import FicheroAPIClient
import Foundation
import OpenAPIRuntime

// MARK: - Region curation (2026-08-29); split into its own file (#5039). Uses the service's client
// and converter; the cache stays private behind `replaceCachedArtifact`.
extension ArtifactService {
    /// One region-curation edit against an artifact's `ocr_geometry.boxes`,
    /// addressed the way the engine addresses boxes: by FULL-list index.
    /// Every call is one audited, undoable server action; the response
    /// carries the fresh geometry so the caller re-renders from it instead
    /// of re-fetching (stale-overlay class of bug).
    private func editRegions(
        artifactId: String,
        documentId: String,
        operation: Components.Schemas.RegionEditOp,
        indices: [Int] = [],
        bbox: [Double]? = nil,
        text: String? = nil
    ) async throws -> Artifact {
        let request = Components.Schemas.ArtifactRegionsEditRequest(
            op: operation,
            indices: indices,
            bbox: bbox,
            text: text
        )
        let response = try await client.api.editArtifactRegionsApiArtifactsArtifactIdRegionsPut(.init(
            path: .init(artifactId: artifactId),
            body: .json(request)
        ))

        switch response {
        case .ok(let okResponse):
            let updated = try convertToArtifact(try okResponse.body.json)
            replaceCachedArtifact(updated, artifactId: artifactId, documentId: documentId)
            return updated
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ArtifactServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ArtifactServiceError.unexpectedResponse(statusCode)
        }
    }

    /// The region edit answers `ArtifactRegionsEditResponse`: every `ArtifactResponse` field
    /// plus `audit_id` (#4941, so ⌘Z can name the action to invert). The engine made it a
    /// superset so existing callers decode unchanged -- true in JSON, but the generator flattens
    /// it into a DIFFERENT Swift type, and this caller stopped compiling at the contract sync.
    ///
    /// Re-decoding the same JSON as `ArtifactResponse` (whose synthesized decoder ignores the
    /// extra key) keeps every field by construction. A hand-written field-by-field copy would
    /// silently drop whatever field `ArtifactResponse` gains next. `audit_id` is not used yet;
    /// wiring ⌘Z for region edits is the archive lane's `source.editor.system-undo`.
    func convertToArtifact(_ edited: Components.Schemas.ArtifactRegionsEditResponse) throws -> Artifact {
        let json = try JSONEncoder().encode(edited)
        return convertToArtifact(try JSONDecoder().decode(Components.Schemas.ArtifactResponse.self, from: json))
    }

    /// Create a bare `regions` artifact to hold hand-drawn boxes on a page
    /// that has no geometry artifact yet (marquee promotion, 2026-08-29).
    func createRegionsArtifact(documentId: String) async throws -> Artifact {
        let request = Components.Schemas.ArtifactCreateRequest(
            documentId: documentId,
            artifactType: "regions",
            provider: "user"
        )
        let response = try await client.api.createArtifactApiArtifactsPost(.init(
            body: .json(request)
        ))
        switch response {
        case .ok(let okResponse):
            let created = convertToArtifact(try okResponse.body.json)
            clearCache(forDocumentId: documentId)
            return created
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ArtifactServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ArtifactServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Reposition one region's bbox (drag-to-move, committed on mouse-up).
    func moveRegion(
        artifactId: String, documentId: String, index: Int, bbox: [Double]
    ) async throws -> Artifact {
        try await editRegions(
            artifactId: artifactId, documentId: documentId,
            operation: .move, indices: [index], bbox: bbox
        )
    }

    /// Remove regions (Delete key). Server-side this is undoable and logged
    /// in the geometry's curation_log — curation-grade, never lossy.
    func deleteRegions(
        artifactId: String, documentId: String, indices: [Int]
    ) async throws -> Artifact {
        try await editRegions(
            artifactId: artifactId, documentId: documentId,
            operation: .delete, indices: indices
        )
    }

    /// Append a hand-drawn region (rubber-band promotion). Text is optional —
    /// a drawn region usually starts without one.
    func addRegion(
        artifactId: String, documentId: String, bbox: [Double], text: String = ""
    ) async throws -> Artifact {
        try await editRegions(
            artifactId: artifactId, documentId: documentId,
            operation: .add, bbox: bbox, text: text
        )
    }

    /// Merge regions: union bbox, texts concatenated in READING order (the
    /// server decides the order — click order is not reading order).
    func combineRegions(
        artifactId: String, documentId: String, indices: [Int]
    ) async throws -> Artifact {
        try await editRegions(
            artifactId: artifactId, documentId: documentId,
            operation: .combine, indices: indices
        )
    }

}
