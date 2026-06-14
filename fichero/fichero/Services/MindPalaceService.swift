import FicheroAPIClient
import Foundation
import OpenAPIRuntime

/// Service wrapper over the generated client for the Mind Palace
/// (`/api/mind-palace`) spatial endpoints.
///
/// The list endpoints return the generic `MindPalaceListResponse` envelope
/// whose `items` are untyped (`OpenAPIValueContainer`), so this service
/// decodes each item into the Phase-1 view-models in `SpatialModels.swift`
/// via a JSON round-trip using `.convertFromSnakeCase`.
///
/// Per `feedback_kg_logic_in_backend`, this layer only reads/persists
/// backend-owned spatial state (positions, connections, viewport). It never
/// computes layout. Phase 1 is read-only; `saveViewport` is provided for
/// Phase 2 and follows the OpenAPI-typed-body rule (Rule 4).
@MainActor
final class MindPalaceService: ObservableObject {
    private let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    enum ServiceError: Error {
        case validationError(String)
        case unexpectedResponse(Int)
    }

    /// JSON decoder configured to map backend snake_case keys onto the
    /// camelCase view-model properties.
    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    private static let encoder = JSONEncoder()

    /// Decode a single untyped envelope item into a view-model. Returns nil
    /// for any item that fails to decode so one malformed row can't drop the
    /// whole scene.
    private func decodeItem<T: Decodable>(_ container: OpenAPIRuntime.OpenAPIValueContainer) -> T? {
        guard let data = try? Self.encoder.encode(container) else { return nil }
        return try? Self.decoder.decode(T.self, from: data)
    }

    private func decodeItems<T: Decodable>(_ items: [OpenAPIRuntime.OpenAPIValueContainer]) -> [T] {
        items.compactMap { decodeItem($0) }
    }

    // MARK: - Rooms

    /// List spatial rooms in the current library.
    func listRooms() async throws -> [MindPalaceRoom] {
        let response = try await client.api.listRoomsApiMindPalaceRoomsGet(
            query: .init(),
        )
        switch response {
        case .ok(let okResponse):
            return decodeItems(try okResponse.body.json.items)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Nodes

    /// List the nodes placed in a room, at their backend-provided positions.
    func listNodes(roomId: String) async throws -> [MindPalaceNode] {
        let response = try await client.api.listNodesApiMindPalaceNodesGet(
            query: .init(roomId: roomId),
        )
        switch response {
        case .ok(let okResponse):
            return decodeItems(try okResponse.body.json.items)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// Persist a node's 3D position after drag-to-move.
    @discardableResult
    func moveNode(
        nodeId: String,
        positionX: Double,
        positionY: Double,
        positionZ: Double,
        scale: Double? = nil
    ) async throws -> MindPalaceNode? {
        let body = Components.Schemas.NodeMoveRequest(
            positionX: positionX,
            positionY: positionY,
            positionZ: positionZ,
            scale: scale
        )
        let response = try await client.api.moveNodeApiMindPalaceNodesNodeIdPatch(
            path: .init(nodeId: nodeId),
            body: .json(body)
        )
        switch response {
        case .ok(let okResponse):
            let node = try okResponse.body.json
            guard let data = try? Self.encoder.encode(node) else { return nil }
            return try? Self.decoder.decode(MindPalaceNode.self, from: data)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Connections

    /// List the connections (edges) between nodes in a room.
    func listConnections(roomId: String) async throws -> [MindPalaceConnection] {
        let response = try await client.api.listConnectionsApiMindPalaceConnectionsGet(
            query: .init(roomId: roomId),
        )
        switch response {
        case .ok(let okResponse):
            return decodeItems(try okResponse.body.json.items)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Viewport

    /// Fetch the saved camera/zoom for a room (per user). Returns nil if the
    /// backend has no stored viewport yet.
    func getViewport(roomId: String, userId: String = "user") async throws -> MindPalaceViewport? {
        let response = try await client.api.getViewportApiMindPalaceRoomsRoomIdViewportUserIdGet(
            path: .init(roomId: roomId, userId: userId),
        )
        switch response {
        case .ok(let okResponse):
            let viewport = try okResponse.body.json
            guard let data = try? Self.encoder.encode(viewport) else { return nil }
            return try? Self.decoder.decode(MindPalaceViewport.self, from: data)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// Persist the camera/zoom for a room (Phase 2 — drag/pan support).
    /// Uses the OpenAPI-typed `ViewportSaveRequest` body, not
    /// `additionalProperties` (Rule 4).
    @discardableResult
    func saveViewport(
        roomId: String,
        userId: String = "user",
        cameraX: Double,
        cameraY: Double,
        cameraZ: Double,
        zoomLevel: Double,
        focusNodeId: String? = nil,
        bookmarkName: String? = nil
    ) async throws -> MindPalaceViewport? {
        // Argument order matches the generated init (OpenAPI property order:
        // bookmark_name, camera_x/y/z, focus_node_id, metadata, zoom_level).
        // `metadata` is optional and omitted.
        let body = Components.Schemas.ViewportSaveRequest(
            cameraX: cameraX,
            cameraY: cameraY,
            cameraZ: cameraZ,
            focusNodeId: focusNodeId,
            zoomLevel: zoomLevel,
            bookmarkName: bookmarkName
        )
        let response = try await client.api.saveViewportApiMindPalaceRoomsRoomIdViewportUserIdPost(
            path: .init(roomId: roomId, userId: userId),
            body: .json(body)
        )
        switch response {
        case .ok(let okResponse):
            let viewport = try okResponse.body.json
            guard let data = try? Self.encoder.encode(viewport) else { return nil }
            return try? Self.decoder.decode(MindPalaceViewport.self, from: data)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Room CRUD

    /// Create a new spatial room.
    @discardableResult
    func createRoom(name: String) async throws -> MindPalaceRoom? {
        let response = try await client.api.createRoomApiMindPalaceRoomsPost(
            body: .json(.init(name: name))
        )
        switch response {
        case .ok(let okResponse):
            let room = try okResponse.body.json
            guard let data = try? Self.encoder.encode(room) else { return nil }
            return try? Self.decoder.decode(MindPalaceRoom.self, from: data)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// Delete a room (the room is a view; underlying documents are untouched).
    func deleteRoom(roomId: String) async throws {
        let response = try await client.api.deleteRoomApiMindPalaceRoomsRoomIdDelete(
            path: .init(roomId: roomId),
        )
        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Stacks

    /// List the stacks (groups/layers) in a room.
    func listStacks(roomId: String) async throws -> [MindPalaceStack] {
        let response = try await client.api.listStacksApiMindPalaceStacksGet(
            query: .init(roomId: roomId),
        )
        switch response {
        case .ok(let okResponse):
            return decodeItems(try okResponse.body.json.items)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Add sources (A5) — place_node

    /// Place a node in a room, tying it to a source document via `source_id`
    /// (`feedback_kg_logic_in_backend`: the backend owns placement). Uses the
    /// OpenAPI-typed `NodeCreateRequest` body (Rule 4). Position is left to the
    /// backend default unless supplied.
    @discardableResult
    func placeNode(
        roomId: String,
        nodeType: Components.Schemas.NodeType,
        sourceId: String? = nil,
        label: String? = nil
    ) async throws -> Bool {
        // Argument order matches the generated init (room_id, node_type,
        // source_id, label, …); remaining fields default on the backend.
        let body = Components.Schemas.NodeCreateRequest(
            roomId: roomId,
            nodeType: nodeType,
            sourceId: sourceId,
            label: label
        )
        let response = try await client.api.placeNodeApiMindPalaceNodesPost(
            body: .json(body)
        )
        switch response {
        case .ok:
            return true
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Arrange (#1269 — also the AI's re-arrangement entry point)

    /// Ask the backend to suggest/apply an arrangement for the given nodes.
    /// The AI drives this same endpoint when it re-arranges the palace.
    func suggestArrangement(
        roomId: String,
        nodeIds: [String],
        arrangementType: Components.Schemas.ArrangementType
    ) async throws {
        let response = try await client.api.suggestArrangementApiMindPalaceRoomsRoomIdSuggestArrangementPost(
            path: .init(roomId: roomId),
            body: .json(.init(nodeIds: nodeIds, arrangementType: arrangementType))
        )
        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }
}

// MARK: - Phase 3: whole-library projection (#1297 follow-up)

extension MindPalaceService {

    static let libraryProjectionDocumentCap = 500
    static let libraryProjectionEntityCap = 500
    static let libraryProjectionClaimCap = 2000

    /// Build the whole-library projection by composing `/api/documents`,
    /// `/api/entities`, and `/api/claims`. Pure-data assembly lives in
    /// `MindPalaceLibraryProjector.project(_:)`.
    func loadLibraryProjection() async throws -> MindPalaceLibraryProjection {
        async let documents = listLibraryDocuments(limit: Self.libraryProjectionDocumentCap)
        async let entities = listLibraryEntities(limit: Self.libraryProjectionEntityCap)
        async let claims = listLibraryClaims(limit: Self.libraryProjectionClaimCap)

        let (docs, ents, cls) = try await (documents, entities, claims)
        let input = MindPalaceLibraryProjector.makeInput(
            documents: docs,
            entities: ents,
            claims: cls
        )
        return MindPalaceLibraryProjector.project(input)
    }

    private func listLibraryDocuments(limit: Int) async throws -> [Components.Schemas.Document] {
        let response = try await client.api.listDocumentsApiDocumentsGet(
            query: .init(limit: limit),
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    private func listLibraryEntities(limit: Int) async throws -> [Components.Schemas.KnowledgeEntity] {
        let response = try await client.api.listEntitiesApiEntitiesGet(
            query: .init(limit: limit),
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    private func listLibraryClaims(limit: Int) async throws -> [Components.Schemas.KnowledgeClaim] {
        let response = try await client.api.listClaimsApiClaimsGet(
            query: .init(limit: limit),
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }
}
