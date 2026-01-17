import Foundation
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ArtifactService")

/// Service for interacting with the Artifact API
@MainActor
class ArtifactService: ObservableObject {
    private let apiClient: APIClient

    /// Cached artifacts by document ID
    @Published private(set) var artifactsByDocument: [String: [Artifact]] = [:]

    /// Loading state per document
    @Published private(set) var loadingDocuments: Set<String> = []

    init(apiClient: APIClient) {
        self.apiClient = apiClient
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

        var path = "/artifacts/document/\(documentId)"
        if let type = type {
            path += "?artifact_type=\(type)"
        }

        let response: ArtifactListResponse = try await apiClient.get(path)
        let artifacts = response.artifacts

        // Cache the results
        artifactsByDocument[documentId] = artifacts

        logger.info("Fetched \(artifacts.count) artifacts for document \(documentId)")
        return artifacts
    }

    /// Get a specific artifact by ID
    func getArtifact(id: String) async throws -> Artifact {
        let artifact: Artifact = try await apiClient.get("/artifacts/\(id)")
        return artifact
    }

    /// Get all artifact types in the library
    func getArtifactTypes() async throws -> [String] {
        let types: [String] = try await apiClient.get("/artifacts/types")
        return types
    }

    /// Delete an artifact
    func deleteArtifact(id: String, documentId: String) async throws {
        try await apiClient.delete("/artifacts/\(id)")

        // Update cache
        if var artifacts = artifactsByDocument[documentId] {
            artifacts.removeAll { $0.id == id }
            artifactsByDocument[documentId] = artifacts
        }

        logger.info("Deleted artifact \(id)")
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
}

// MARK: - Response Models

struct ArtifactListResponse: Codable {
    let artifacts: [Artifact]
    let total: Int
}
