import Foundation
import OSLog
import FicheroAPIClient
import OpenAPIRuntime

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "ArtifactServiceGenerated")

/// ArtifactService using the generated OpenAPI client.
/// Manages document artifacts (transcripts, descriptions, etc.)
@MainActor
class ArtifactServiceGenerated: ObservableObject {
    private let client: FicheroClient

    /// Cached artifacts by document ID
    @Published private(set) var artifactsByDocument: [String: [Artifact]] = [:]

    /// Loading state per document
    @Published private(set) var loadingDocuments: Set<String> = []

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    // MARK: - Fetch Artifacts

    /// Fetch all artifacts for a document
    func getArtifacts(
        forDocumentId documentId: String,
        type: String? = nil,
        forceRefresh: Bool = false
    ) async throws -> [Artifact] {
        // Return cached if available and not forcing refresh
        if !forceRefresh, let cached = artifactsByDocument[documentId] {
            if let type = type {
                return cached.filter { $0.artifactType == type }
            }
            return cached
        }

        loadingDocuments.insert(documentId)
        defer { loadingDocuments.remove(documentId) }

        let response = try await client.api.listDocumentArtifactsApiArtifactsDocumentDocIdGet(
            path: .init(docId: documentId),
            query: .init(artifactType: type),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let okResponse):
            let artifactList = try okResponse.body.json
            let artifacts = artifactList.artifacts.map { convertToArtifact($0) }

            // Cache the results
            artifactsByDocument[documentId] = artifacts

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
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
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
        let response = try await client.api.listArtifactTypesApiArtifactsTypesGet(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ArtifactServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ArtifactServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get all artifacts in the library (uses direct HTTP call since generated client may not have this endpoint)
    func getAllArtifacts(type: String? = nil, limit: Int = 100, offset: Int = 0) async throws -> [Artifact] {
        var urlString = "http://localhost:8765/api/artifacts?limit=\(limit)&offset=\(offset)"
        if let type = type {
            urlString += "&artifact_type=\(type.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? type)"
        }

        guard let url = URL(string: urlString) else {
            throw ArtifactServiceError.serverError("Invalid URL")
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        if let libraryPath = client.currentLibraryPath {
            request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
        }

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw ArtifactServiceError.unexpectedResponse(-1)
        }

        guard httpResponse.statusCode == 200 else {
            throw ArtifactServiceError.unexpectedResponse(httpResponse.statusCode)
        }

        let decoder = JSONDecoder()
        let artifactList = try decoder.decode(AllArtifactsResponse.self, from: data)

        logger.info("Fetched \(artifactList.artifacts.count) total artifacts")
        return artifactList.artifacts.map { convertToArtifactFromJSON($0) }
    }

    // MARK: - JSON Conversion for direct HTTP calls

    private func convertToArtifactFromJSON(_ json: ArtifactJSON) -> Artifact {
        // Parse date from string
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let createdAt = formatter.date(from: json.createdAt) ?? Date()

        // Convert data dict
        var data: [String: AnyCodable]?
        if let jsonData = json.data, !jsonData.isEmpty {
            var dict: [String: AnyCodable] = [:]
            for (key, value) in jsonData {
                dict[key] = AnyCodable(value)
            }
            data = dict
        }

        return Artifact(
            id: json.id,
            documentId: json.documentId,
            version: json.version,
            artifactType: json.artifactType,
            content: json.content,
            data: data,
            provider: json.provider,
            model: json.model,
            reviewed: json.reviewed,
            createdAt: createdAt
        )
    }

    /// Delete an artifact
    func deleteArtifact(id: String, documentId: String) async throws {
        let response = try await client.api.deleteArtifactApiArtifactsArtifactIdDelete(
            path: .init(artifactId: id),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .noContent:
            // Update cache
            if var artifacts = artifactsByDocument[documentId] {
                artifacts.removeAll { $0.id == id }
                artifactsByDocument[documentId] = artifacts
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
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let createdAt = formatter.date(from: generated.createdAt) ?? Date()

        return Artifact(
            id: generated.id,
            documentId: generated.documentId,
            version: generated.version,
            artifactType: generated.artifactType,
            content: generated.content,
            data: data,
            provider: generated.provider,
            model: generated.model,
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

// MARK: - JSON Types for Direct HTTP Calls

/// Response for list all artifacts endpoint
private struct AllArtifactsResponse: Codable {
    let artifacts: [ArtifactJSON]
    let total: Int
}

/// JSON artifact representation for direct HTTP decoding
private struct ArtifactJSON: Codable {
    let id: String
    let documentId: String
    let artifactType: String
    let content: String?
    let data: [String: AnyCodable]?
    let version: Int
    let provider: String?
    let model: String?
    let confidence: Double?
    let reviewed: Bool
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case documentId = "document_id"
        case artifactType = "artifact_type"
        case content
        case data
        case version
        case provider
        case model
        case confidence
        case reviewed
        case createdAt = "created_at"
    }
}
