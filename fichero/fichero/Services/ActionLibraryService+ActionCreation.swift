import FicheroAPIClient
import Foundation
import OSLog

extension ActionLibraryService {
    // MARK: - Action Creation Helpers

    /// Create action from workflow node
    func createFromNode(
        name: String,
        node: [String: Any],
        description: String = "",
        category: String = "custom",
        tags: [String] = []
    ) async throws -> ActionItem {
        let response = try await client.api.createActionFromNodeApiActionsFromNodePost(
            body: .json(.init(
                name: name,
                node: .init(additionalProperties: try objectContainer(from: node)),
                description: description,
                category: category,
                tags: tags
            ))
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json, as: ActionItem.self)
        case .unprocessableContent, .undocumented:
            throw ActionLibraryError.serverError
        }
    }

    /// Create composite action from multiple nodes
    func createComposite(
        name: String,
        nodes: [[String: Any]],
        edges: [[String: Any]],
        description: String = "",
        category: String = "custom",
        tags: [String] = []
    ) async throws -> ActionItem {
        let nodePayloads = try nodes.map {
            Components.Schemas.CreateCompositeRequest.NodesPayloadPayload(
                additionalProperties: try objectContainer(from: $0)
            )
        }
        let edgePayloads = try edges.map {
            Components.Schemas.CreateCompositeRequest.EdgesPayloadPayload(
                additionalProperties: try objectContainer(from: $0)
            )
        }
        let response = try await client.api.createCompositeActionApiActionsCompositePost(
            body: .json(.init(
                name: name,
                nodes: nodePayloads,
                edges: edgePayloads,
                description: description,
                category: category,
                tags: tags
            ))
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json, as: ActionItem.self)
        case .unprocessableContent, .undocumented:
            throw ActionLibraryError.serverError
        }
    }
}
