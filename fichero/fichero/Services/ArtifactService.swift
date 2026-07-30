import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ArtifactService")

/// ArtifactService using the generated OpenAPI client.
/// Manages document artifacts (transcripts, descriptions, etc.)
@MainActor
@Observable
class ArtifactService {
    private let client: FicheroClient

    /// Cached artifacts by document ID
    private(set) var artifactsByDocument: [String: [Artifact]] = [:]

    /// Loading state per document
    private(set) var loadingDocuments: Set<String> = []

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    // MARK: - Fetch Artifacts

    /// Fetch all artifacts for a document.
    ///
    /// `includeDescendants` controls whether the backend aggregates artifacts
    /// from children and parent (legacy V1 behavior, default true) or scopes
    /// strictly to the requested document (V2). The aggregation caused
    /// "delete pops back" confusion in V2 because deleting one artifact left
    /// a sibling in place that looked like the same one.
    func getArtifacts(
        forDocumentId documentId: String,
        type: String? = nil,
        forceRefresh: Bool = false,
        includeDescendants: Bool = true
    ) async throws -> [Artifact] {
        // Cache key needs the scope flag so V1 and V2 don't share entries.
        let cacheKey = includeDescendants ? documentId : "\(documentId)|own"
        if !forceRefresh, let cached = artifactsByDocument[cacheKey] {
            if let type = type {
                return cached.filter { $0.artifactType == type }
            }
            return cached
        }

        loadingDocuments.insert(documentId)
        defer { loadingDocuments.remove(documentId) }

        let response = try await client.api.listDocumentArtifactsApiArtifactsDocumentDocIdGet(
            path: .init(docId: documentId),
            query: .init(artifactType: type, includeDescendants: includeDescendants),
        )

        switch response {
        case .ok(let okResponse):
            let artifactList = try okResponse.body.json
            let artifacts = artifactList.items.map { convertToArtifact($0) }

            artifactsByDocument[cacheKey] = artifacts

            logger.info("Fetched \(artifacts.count) artifacts for document \(documentId)")
            return artifacts
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ArtifactServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ArtifactServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get a specific artifact by ID
    func getArtifact(id: String) async throws -> Artifact {
        let response = try await client.api.getArtifactApiArtifactsArtifactIdGet(
            path: .init(artifactId: id),
        )

        switch response {
        case .ok(let okResponse):
            let artifact = try okResponse.body.json
            return convertToArtifact(artifact)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ArtifactServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ArtifactServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get all artifact types in the library
    func getArtifactTypes() async throws -> [String] {
        let response = try await client.api.listArtifactTypesApiArtifactsTypesGet()

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .undocumented(let statusCode, _):
            throw ArtifactServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get all artifacts in the library.
    func getAllArtifacts(type: String? = nil, limit: Int = 100, offset: Int = 0) async throws -> [Artifact] {
        let response = try await client.api.listAllArtifactsApiArtifactsGet(
            query: .init(artifactType: type, limit: limit, offset: offset),
        )

        switch response {
        case .ok(let okResponse):
            let artifactList = try okResponse.body.json
            logger.info("Fetched \(artifactList.items.count) total artifacts")
            return artifactList.items.map { convertToArtifact($0) }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ArtifactServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ArtifactServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Update an artifact's editable fields (content, reviewed flag).
    /// Provenance fields (provider, model, version) stay set by the tool
    /// that produced the artifact.
    func updateArtifact(
        id: String,
        documentId: String,
        content: String? = nil,
        reviewed: Bool? = nil
    ) async throws -> Artifact {
        let request = Components.Schemas.ArtifactUpdate(
            content: content,
            reviewed: reviewed
        )
        let response = try await client.api.updateArtifactApiArtifactsArtifactIdPut(.init(
            path: .init(artifactId: id),
            body: .json(request)
        ))

        switch response {
        case .ok(let okResponse):
            let json = try okResponse.body.json
            let updated = convertToArtifact(json)

            for key in [documentId, "\(documentId)|own"] {
                if var cached = artifactsByDocument[key] {
                    if let index = cached.firstIndex(where: { $0.id == id }) {
                        cached[index] = updated
                    } else {
                        cached.append(updated)
                    }
                    artifactsByDocument[key] = cached
                }
            }
            return updated
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ArtifactServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ArtifactServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Delete an artifact
    func deleteArtifact(id: String, documentId: String) async throws {
        let response = try await client.api.deleteArtifactApiArtifactsArtifactIdDelete(
            path: .init(artifactId: id),
        )

        switch response {
        case .noContent:
            // Update both cache scopes — V1 (aggregated) and V2 (own-only)
            // can both have entries for the doc keyed differently.
            for key in [documentId, "\(documentId)|own"] {
                if var artifacts = artifactsByDocument[key] {
                    artifacts.removeAll { $0.id == id }
                    artifactsByDocument[key] = artifacts
                }
            }
            logger.info("Deleted artifact \(id)")
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ArtifactServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ArtifactServiceError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Cache Management

    /// Clear cached artifacts for a document
    func clearCache(forDocumentId documentId: String) {
        artifactsByDocument.removeValue(forKey: documentId)
    }

    /// Clear all cached artifacts
    func clearAllCache() {
        artifactsByDocument.removeAll()
    }

    /// Check if we're loading artifacts for a document
    func isLoading(documentId: String) -> Bool {
        loadingDocuments.contains(documentId)
    }

    // MARK: - Type Conversions

    private func convertToArtifact(_ generated: Components.Schemas.ArtifactResponse) -> Artifact {
        // Convert data dict
        var data: [String: AnyCodable]?
        if let genData = generated.data {
            var dict: [String: AnyCodable] = [:]
            for (key, value) in genData.additionalProperties.value {
                if let unwrapped = value {
                    dict[key] = AnyCodable(unwrapped)
                }
            }
            data = dict.isEmpty ? nil : dict
        }

        // Parse date from string
        // Use the multi-format parser; falling back to Date() (today) silently
        // mis-dated artifacts whose timestamp didn't match the rigid format.
        // (Audit class F.)
        let createdAt = parseEngineDate(generated.createdAt) ?? Date()

        return Artifact(
            id: generated.id,
            documentId: generated.documentId,
            sourceArtifactId: generated.sourceArtifactId,
            version: generated.version,
            artifactType: generated.artifactType,
            content: generated.content,
            data: data,
            // Present only on the single-artifact GET (#4309); list payloads
            // omit geometry to stay lean.
            ocrGeometry: generated.ocrGeometry.map { OCRGeometry(generated: $0) },
            // Run provenance (#4313/#4319): the browser groups by run and
            // orders by pipeline sequence, so these must survive conversion.
            runId: generated.runId,
            provider: generated.provider,
            model: generated.model,
            stepName: generated.stepName,
            workflowId: generated.workflowId,
            sequence: generated.sequence,
            confidence: generated.confidence,
            reviewed: generated.reviewed,
            createdAt: createdAt
        )
    }
}

// MARK: - Error Types

enum ArtifactServiceError: Error, LocalizedError {
    case unexpectedResponse(Int)
    case serverError(String)

    var errorDescription: String? {
        switch self {
        case .unexpectedResponse(let code):
            return "Unexpected response from artifact service (status: \(code))"
        case .serverError(let message):
            return "Server error: \(message)"
        }
    }
}
