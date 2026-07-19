import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

extension EntityService {
    // MARK: - Knowledge Graph endpoint wiring (#1422)

    func generateKGEntityBiography(_ entityId: String) async throws -> Data {
        try await endpointData(path: "/api/kg/entities/\(entityId)/bio", method: "POST")
    }

    func kgEntityCurationCandidates(limit: Int = 50) async throws -> Data {
        try await endpointData(
            path: "/api/kg/entity-curation/candidates",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    /// Semantic (embedding) entity search — returns entities similar to `q`
    /// with a `similarity_score`, catching name variants + cross-script
    /// duplicates that structural co-occurrence misses (#3317). `entityType`
    /// constrains to the same kind.
    func searchEntitiesSemantic(
        query: String,
        entityType: String? = nil,
        limit: Int = 20
    ) async throws -> Data {
        var items = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "limit", value: "\(limit)")
        ]
        if let entityType {
            items.append(URLQueryItem(name: "entity_type", value: entityType))
        }
        return try await endpointData(
            path: "/api/kg/entity-curation/semantic",
            queryItems: items
        )
    }

    func kgGraphCentrality(limit: Int = 25) async throws -> Data {
        try await endpointData(
            path: "/api/kg/graph/centrality",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func kgGraphClustering() async throws -> Data {
        try await endpointData(path: "/api/kg/graph/clustering")
    }

    func kgGraphCommunities() async throws -> Data {
        try await endpointData(path: "/api/kg/graph/communities")
    }

    func kgGraphComponents() async throws -> Data {
        try await endpointData(path: "/api/kg/graph/components")
    }

    func kgGraphCooccurrence(_ entityId: String, limit: Int = 25) async throws -> Data {
        try await endpointData(
            path: "/api/kg/graph/cooccurrence/\(entityId)",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func kgGraphMetrics() async throws -> Data {
        try await endpointData(path: "/api/kg/graph/metrics")
    }

    func kgGraphPagerank(limit: Int = 25) async throws -> Data {
        try await endpointData(
            path: "/api/kg/graph/pagerank",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func kgGraphPath(from sourceEntityId: String, to targetEntityId: String) async throws -> Data {
        try await endpointData(
            path: "/api/kg/graph/path",
            queryItems: [
                URLQueryItem(name: "source_entity_id", value: sourceEntityId),
                URLQueryItem(name: "target_entity_id", value: targetEntityId)
            ]
        )
    }

    func kgGraphSimilar(_ entityId: String, limit: Int = 25) async throws -> Data {
        try await endpointData(
            path: "/api/kg/graph/similar/\(entityId)",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func kgGraphTraverse(_ entityId: String, depth: Int = 2) async throws -> Data {
        try await endpointData(
            path: "/api/kg/graph/traverse/\(entityId)",
            queryItems: [URLQueryItem(name: "depth", value: "\(depth)")]
        )
    }

    func kgGraphTriangles(_ entityId: String) async throws -> Data {
        try await endpointData(path: "/api/kg/graph/triangles/\(entityId)")
    }

    func upsertKGInclusion(_ body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/kg/inclusion", method: "POST", jsonBody: body)
    }

    func listKGInclusions() async throws -> Data {
        try await endpointData(path: "/api/kg/inclusion")
    }

    func kgMutations(limit: Int = 50) async throws -> Data {
        try await endpointData(
            path: "/api/kg/mutations",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func undoKGMutation(_ mutationId: String) async throws -> Data {
        try await endpointData(path: "/api/kg/mutations/\(mutationId)/undo", method: "POST")
    }

    func applyKGPredictionRun(_ runId: String, body: [String: Any] = [:]) async throws -> Data {
        try await endpointData(path: "/api/kg/predictions/\(runId)/apply", method: "POST", jsonBody: body)
    }

    func deletePyKEENModel(_ modelId: String) async throws {
        _ = try await endpointData(path: "/api/kg/pykeen/models/\(modelId)", method: "DELETE")
    }

    func pyKEENPredictions(entityId: String, limit: Int = 25) async throws -> Data {
        try await endpointData(
            path: "/api/kg/pykeen/predict/\(entityId)",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func storedPyKEENPredictions() async throws -> Data {
        try await endpointData(path: "/api/kg/pykeen/stored")
    }

    func storedPyKEENPrediction(_ predictionId: String) async throws -> Data {
        try await endpointData(path: "/api/kg/pykeen/stored/\(predictionId)")
    }

    func verifyStoredPyKEENPrediction(_ predictionId: String, body: [String: Any]) async throws -> Data {
        try await endpointData(
            path: "/api/kg/pykeen/stored/\(predictionId)/verify",
            method: "PATCH",
            jsonBody: body
        )
    }

    func trainPyKEEN(_ body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/kg/pykeen/train", method: "POST", jsonBody: body)
    }

    func pyKEENTrainingJobs() async throws -> Data {
        try await endpointData(path: "/api/kg/pykeen/training-jobs")
    }

    func pyKEENTrainingJob(_ modelId: String) async throws -> Data {
        try await endpointData(path: "/api/kg/pykeen/training-jobs/\(modelId)")
    }

    // PyKEEN prediction review queue (#3677 store-layer coverage). Routes the
    // `/api/kg/pykeen/reviews` endpoints through the service layer like the rest
    // of the PyKEEN surface, so views read them via the store, not the raw client.
    func pyKEENReviews() async throws -> Data {
        try await endpointData(path: "/api/kg/pykeen/reviews")
    }

    func createPyKEENReview(_ body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/kg/pykeen/reviews", method: "POST", jsonBody: body)
    }

    func updatePyKEENReview(_ reviewId: String, body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/kg/pykeen/reviews/\(reviewId)", method: "PATCH", jsonBody: body)
    }

    // Content-representations Reader surface (#3677 store-layer coverage). The
    // Reader's derived-content/knowledge layer reads a document's representations
    // and their revision history through the service layer, not the raw client —
    // same endpointData path the rest of the knowledge surface uses.
    func contentRepresentations(documentId: String) async throws -> Data {
        try await endpointData(path: "/api/content-representations/document/\(documentId)")
    }

    func contentRepresentationRevisions(_ representationId: String) async throws -> Data {
        try await endpointData(path: "/api/content-representations/\(representationId)/revisions")
    }

    func createContentRepresentationRevision(
        _ representationId: String,
        body: [String: Any]
    ) async throws -> Data {
        try await endpointData(
            path: "/api/content-representations/\(representationId)/revisions",
            method: "POST",
            jsonBody: body
        )
    }

    // Multi-user workspace-membership admin (#3561 / #3677 store-layer coverage).
    // PATCHes a chat workspace's member set through the service layer so the
    // multi-user admin surface reaches it via the store, not the raw client.
    func updateChatWorkspaceMembers(
        _ workspaceId: String,
        body: [String: Any]
    ) async throws -> Data {
        try await endpointData(
            path: "/api/chat/workspaces/\(workspaceId)/members",
            method: "PATCH",
            jsonBody: body
        )
    }

    func rebuildKnowledgeGraph(_ body: [String: Any] = [:]) async throws -> Data {
        try await endpointData(path: "/api/kg/rebuild", method: "POST", jsonBody: body)
    }

    func renderKGParagraph(_ body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/kg/render/paragraph", method: "POST", jsonBody: body)
    }

    func resetKnowledgeGraph(_ body: [String: Any] = [:]) async throws -> Data {
        try await endpointData(path: "/api/kg/reset", method: "POST", jsonBody: body)
    }

    func kgReviewGraphCandidates(limit: Int = 50) async throws -> Data {
        try await endpointData(
            path: "/api/kg/review/graph-candidates",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func kgReviewLabels() async throws -> Data {
        try await endpointData(path: "/api/kg/review/labels")
    }

    func kgReviewPairs(limit: Int = 50) async throws -> Data {
        try await endpointData(
            path: "/api/kg/review/pairs",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func queueKGReviewPair(_ body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/kg/review/pairs", method: "POST", jsonBody: body)
    }

    func acceptKGReviewPair(_ pairId: String) async throws -> Data {
        try await endpointData(path: "/api/kg/review/pairs/\(pairId)/accept", method: "POST")
    }

    func rejectKGReviewPair(_ pairId: String) async throws -> Data {
        try await endpointData(path: "/api/kg/review/pairs/\(pairId)/reject", method: "POST")
    }

    func searchKnowledgeGraph(_ query: String, limit: Int = 25) async throws -> Data {
        try await endpointData(
            path: "/api/kg/search",
            queryItems: [
                URLQueryItem(name: "q", value: query),
                URLQueryItem(name: "limit", value: "\(limit)")
            ]
        )
    }

    func runKnowledgeGraphSPARQL(_ query: String) async throws -> Data {
        try await endpointData(
            path: "/api/kg/sparql",
            method: "POST",
            jsonBody: ["query": query]
        )
    }

    func kgTriangulation(limit: Int = 50) async throws -> Data {
        try await endpointData(
            path: "/api/kg/triangulation",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func kgEntityTriangulation(_ entityId: String) async throws -> Data {
        try await endpointData(path: "/api/kg/triangulation/entity/\(entityId)")
    }

    func recomputeKGTriangulation(_ body: [String: Any] = [:]) async throws -> Data {
        try await endpointData(path: "/api/kg/triangulation/recompute", method: "POST", jsonBody: body)
    }
}
