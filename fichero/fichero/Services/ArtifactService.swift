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
    // Internal, not private: `ArtifactService+RegionCuration.swift` shares the client and the converter (#5039).
    let client: FicheroClient

    /// Cached artifacts by document ID
    private(set) var artifactsByDocument: [String: [Artifact]] = [:]

    /// Loading state per document
    private(set) var loadingDocuments: Set<String> = []

    /// The fetch on its way per cache key, so callers share it. Not observed: plumbing.
    @ObservationIgnored private var inFlightFetches: [String: InFlightFetch] = [:]
    /// Bumped by every write and clear: a fetch that started earlier is neither joined nor stored.
    @ObservationIgnored private var writeGeneration = 0

    private struct InFlightFetch {
        let task: Task<[Artifact], Error>
        let generation: Int
    }

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    /// Convenience initializer from APIClient - extracts library path.
    /// Mirrors `ActivityService`, so surfaces that hold only an `APIClient`
    /// (the Activity window, and any run-trace sheet opened outside the
    /// document detail layout) can still fetch a full artifact rather than
    /// being stuck showing a truncated preview.
    convenience init(apiClient: APIClient) {
        let libraryPath = apiClient.currentLibraryPath ?? ""
        let ficheroClient = FicheroClient(
            baseURL: EngineConfig.host,
            libraryPath: libraryPath,
            transportMode: EngineConfig.transportMode
        )
        self.init(ficheroClient: ficheroClient)
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
        let all = try await allArtifacts(
            documentId: documentId, cacheKey: cacheKey,
            includeDescendants: includeDescendants, forceRefresh: forceRefresh
        )
        guard let type else { return all }
        return all.filter { $0.artifactType == type }
    }

    /// The document's FULL artifact list, from the cache, from a fetch already on its way, or
    /// from a new one. Two rules, at the one seam every caller shares (#5003): concurrent
    /// callers JOIN the fetch in flight (a page change asks from five views at once, and the
    /// cache only fills when a response arrives, so each used to send its own request); and the
    /// server is always asked for EVERY type, because a typed request used to store its filtered
    /// answer as the document's whole list. The type filter is applied locally.
    private func allArtifacts(
        documentId: String, cacheKey: String, includeDescendants: Bool, forceRefresh: Bool
    ) async throws -> [Artifact] {
        if let running = inFlightFetches[cacheKey], running.generation == writeGeneration {
            return try await running.task.value
        }
        if !forceRefresh, let cached = artifactsByDocument[cacheKey] { return cached }

        let fetch = Task { @MainActor [client] () throws -> [Artifact] in
            let response = try await client.api.listDocumentArtifactsApiArtifactsDocumentDocIdGet(
                path: .init(docId: documentId),
                query: .init(artifactType: nil, includeDescendants: includeDescendants),
            )
            switch response {
            case .ok(let okResponse):
                return try okResponse.body.json.items.map { self.convertToArtifact($0) }
            case .unprocessableContent(let error):
                let detail = try? error.body.json
                throw ArtifactServiceError.serverError(detail?.detail?.description ?? "Validation error")
            case .undocumented(let statusCode, _):
                throw ArtifactServiceError.unexpectedResponse(statusCode)
            }
        }
        let startedAt = writeGeneration
        inFlightFetches[cacheKey] = InFlightFetch(task: fetch, generation: startedAt)
        loadingDocuments.insert(documentId)
        defer {
            // Only clear the slot if it is still OURS: a newer fetch may have replaced it.
            if inFlightFetches[cacheKey]?.generation == startedAt { inFlightFetches[cacheKey] = nil }
            loadingDocuments.remove(documentId)
        }
        let artifacts = try await fetch.value
        // A write landed while this was on its way: its answer may predate the write, and the
        // write already patched the cache in place. Hand it to this caller, never to the cache.
        guard startedAt == writeGeneration else { return artifacts }
        artifactsByDocument[cacheKey] = artifacts
        logger.info("Fetched \(artifacts.count) artifacts for document \(documentId)")
        return artifacts
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

            writeGeneration += 1
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
            writeGeneration += 1
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
        writeGeneration += 1
        artifactsByDocument.removeValue(forKey: documentId)
    }

    /// Clear all cached artifacts
    func clearAllCache() {
        writeGeneration += 1
        artifactsByDocument.removeAll()
    }

    /// Check if we're loading artifacts for a document
    func isLoading(documentId: String) -> Bool {
        loadingDocuments.contains(documentId)
    }

    /// Replace one cached artifact with the server's fresh copy (a region edit's response), under
    /// both cache keys, so callers re-render from it instead of re-fetching. Bumps the write
    /// generation like every other write, so an older in-flight fetch is not stored over it.
    func replaceCachedArtifact(_ updated: Artifact, artifactId: String, documentId: String) {
        writeGeneration += 1
        for key in [documentId, "\(documentId)|own"] {
            if var cached = artifactsByDocument[key],
               let index = cached.firstIndex(where: { $0.id == artifactId }) {
                cached[index] = updated
                artifactsByDocument[key] = cached
            }
        }
    }

    // MARK: - Type Conversions

    func convertToArtifact(_ generated: Components.Schemas.ArtifactResponse) -> Artifact {
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
