// swiftlint:disable file_length
import Observation
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

/// Canonical service for the Action Library (`/api/actions`).
///
/// Routes every REST call through the generated OpenAPI client
/// (`FicheroClient` → `AuthTokenMiddleware` + `LibraryPathMiddleware`) instead
/// of hand-written `URLSession` requests (#1666/#1711). This is the single
/// transport for all `/api/actions/*` traffic: the former two duplicate
/// services (`ActionsService` + `ActionLibraryService`) both spoke raw
/// `URLRequest` to the same surface; they are now collapsed onto this one type,
/// with `ActionsService` reduced to a thin subclass that only carries the
/// label/return-shape variants its existing call sites depend on.
///
/// Like `IntegrationsService`/`ModelComparisonService`, the localhost client is
/// used purely to carry auth; `LibraryPathMiddleware` injects
/// `X-Fichero-Library-Path` centrally for library-scoped paths (#1710).
@MainActor
@Observable
// swiftlint:disable:next type_body_length
class ActionLibraryService {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "ActionLibraryService")

    var actions: [ActionItem] = []
    var categories: [String] = []
    var recentActions: [ActionItem] = []
    var popularActions: [ActionItem] = []
    var isLoading = false
    var error: String?

    /// Shared generated client — the single transport for both this type and the
    /// `ActionsService` subclass.
    let client: FicheroClient

    init(client: FicheroClient = .localhost) {
        self.client = client
    }

    // MARK: - Response Mapping Helpers

    /// Bridge a generated typed schema (e.g. `ActionResponse`) into the matching
    /// app model. The generated schemas encode to the same snake_case wire bytes
    /// the former `URLSession` decoders consumed, so this is a 1:1 mapping.
    /// `internal` so the `ActionsService` subclass can reuse it.
    func decodeModel<T: Decodable>(from value: some Encodable, as _: T.Type = T.self) throws -> T {
        let data = try JSONEncoder().encode(value)
        return try JSONDecoder().decode(T.self, from: data)
    }

    /// Bridge the free-form `items` container array returned by the list
    /// endpoints (`ActionListResponse.items`) into app models, mirroring the
    /// proven `IntegrationsService`/`NoteService` container-decode pattern.
    func decodeModels<T: Decodable>(from containers: [OpenAPIValueContainer], as _: T.Type = T.self) throws -> [T] {
        try containers.map { container in
            guard let object = container.value else { throw ActionLibraryError.serverError }
            let data = try JSONSerialization.data(withJSONObject: object)
            return try JSONDecoder().decode(T.self, from: data)
        }
    }

    /// Build an `OpenAPIObjectContainer` from a free-form `[String: Any]` node /
    /// graph dictionary for the from-node / composite request bodies.
    func objectContainer(from dict: [String: Any]) throws -> OpenAPIRuntime.OpenAPIObjectContainer {
        let data = try JSONSerialization.data(withJSONObject: dict)
        return try JSONDecoder().decode(OpenAPIRuntime.OpenAPIObjectContainer.self, from: data)
    }

    // MARK: - List Operations

    /// Load all actions
    func loadActions() async {
        isLoading = true
        error = nil

        do {
            let response = try await client.api.listActionsApiActionsGet()
            switch response {
            case .ok(let okResponse):
                actions = try decodeModels(from: try okResponse.body.json.items, as: ActionItem.self)
                logger.info("Loaded \(self.actions.count) actions")
            case .undocumented:
                throw ActionLibraryError.serverError
            }
        } catch {
            self.error = error.localizedDescription
            logger.error("Failed to load actions: \(error.localizedDescription)")
        }

        isLoading = false
    }

    /// Load categories
    func loadCategories() async {
        do {
            let response = try await client.api.listCategoriesApiActionsCategoriesGet()
            switch response {
            case .ok(let okResponse):
                categories = try okResponse.body.json.categories
            case .undocumented:
                return
            }
        } catch {
            logger.error("Failed to load categories: \(error.localizedDescription)")
        }
    }

    /// Load actions by category
    func loadActions(category: String) async -> [ActionItem] {
        do {
            let response = try await client.api.listActionsByCategoryApiActionsCategoryCategoryGet(
                path: .init(category: category),
            )
            switch response {
            case .ok(let okResponse):
                return try decodeModels(from: try okResponse.body.json.items, as: ActionItem.self)
            case .unprocessableContent, .undocumented:
                return []
            }
        } catch {
            logger.error("Failed to load category: \(error.localizedDescription)")
            return []
        }
    }

    /// Load built-in actions
    func loadBuiltinActions() async -> [ActionItem] {
        do {
            let response = try await client.api.listBuiltinActionsApiActionsBuiltinGet()
            switch response {
            case .ok(let okResponse):
                return try decodeModels(from: try okResponse.body.json.items, as: ActionItem.self)
            case .undocumented:
                return []
            }
        } catch {
            logger.error("Failed to load builtin actions: \(error.localizedDescription)")
            return []
        }
    }

    /// Load custom actions
    func loadCustomActions() async -> [ActionItem] {
        do {
            let response = try await client.api.listCustomActionsApiActionsCustomGet()
            switch response {
            case .ok(let okResponse):
                return try decodeModels(from: try okResponse.body.json.items, as: ActionItem.self)
            case .undocumented:
                return []
            }
        } catch {
            logger.error("Failed to load custom actions: \(error.localizedDescription)")
            return []
        }
    }

    /// Load recent actions
    func loadRecentActions(limit: Int = 10) async {
        do {
            let response = try await client.api.listRecentActionsApiActionsRecentGet(
                query: .init(limit: limit),
            )
            switch response {
            case .ok(let okResponse):
                recentActions = try decodeModels(from: try okResponse.body.json.items, as: ActionItem.self)
            case .unprocessableContent, .undocumented:
                return
            }
        } catch {
            logger.error("Failed to load recent actions: \(error.localizedDescription)")
        }
    }

    /// Load the current library's ACL snapshot for the active user.
    func loadLibraryAuthzSnapshot(targetId: String? = nil) async throws -> Components.Schemas.LibraryAuthzSnapshot {
        let response = try await client.api.getLibraryAuthzSnapshotApiAuthzLibraryGet(
            query: .init(targetId: targetId)
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent, .undocumented:
            throw ActionLibraryError.serverError
        }
    }

    /// List this library's members (roles joined with account profiles) for the
    /// sidebar sharing badge/popover (#2869 A4). Owner-gated on the engine when
    /// multi-user is on; callers surface a thrown error as "no access".
    func listLibraryMembers() async throws -> Components.Schemas.LibraryMembersResponse {
        let response = try await client.api.listLibraryMembersApiAuthzMembersGet(.init())
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .undocumented:
            throw ActionLibraryError.serverError
        }
    }

    /// Load popular actions. Sets `popularActions` and also returns the list so
    /// the `ActionsService` subclass can vend it directly to its call sites.
    @discardableResult
    func loadPopularActions(limit: Int = 10) async -> [ActionItem] {
        do {
            let response = try await client.api.listPopularActionsApiActionsPopularGet(
                query: .init(limit: limit),
            )
            switch response {
            case .ok(let okResponse):
                let loaded = try decodeModels(from: try okResponse.body.json.items, as: ActionItem.self)
                popularActions = loaded
                return loaded
            case .unprocessableContent, .undocumented:
                return []
            }
        } catch {
            logger.error("Failed to load popular actions: \(error.localizedDescription)")
            return []
        }
    }

    // MARK: - Search

    /// Search actions
    func search(query: String? = nil, category: String? = nil, tags: [String]? = nil) async -> [ActionItem] {
        do {
            let response = try await client.api.searchActionsApiActionsSearchGet(
                query: .init(
                    query: (query?.isEmpty == false) ? query : nil,
                    category: category,
                    tags: (tags?.isEmpty == false) ? tags?.joined(separator: ",") : nil
                ),
            )
            switch response {
            case .ok(let okResponse):
                return try decodeModels(from: try okResponse.body.json.items, as: ActionItem.self)
            case .unprocessableContent, .undocumented:
                return []
            }
        } catch {
            logger.error("Search failed: \(error.localizedDescription)")
            return []
        }
    }

    // MARK: - CRUD

    /// Get action by ID
    func getAction(_ actionId: String) async -> ActionItem? {
        do {
            let response = try await client.api.getActionApiActionsActionIdGet(
                path: .init(actionId: actionId),
            )
            switch response {
            case .ok(let okResponse):
                return try decodeModel(from: try okResponse.body.json, as: ActionItem.self)
            case .unprocessableContent, .undocumented:
                return nil
            }
        } catch {
            logger.error("Failed to get action: \(error.localizedDescription)")
            return nil
        }
    }

    /// Create a new action
    func createAction(_ action: CreateActionRequest) async throws -> ActionItem {
        let response = try await client.api.createActionApiActionsPost(
            body: .json(.init(
                name: action.name,
                description: action.description,
                category: action.category,
                tags: action.tags,
                icon: action.icon,
                author: action.author
            ))
        )
        switch response {
        case .ok(let okResponse):
            let created: ActionItem = try decodeModel(from: try okResponse.body.json)
            logger.info("Created action: \(created.name)")
            return created
        case .unprocessableContent, .undocumented:
            throw ActionLibraryError.serverError
        }
    }

    /// Delete an action
    func deleteAction(_ actionId: String) async throws {
        let response = try await client.api.deleteActionApiActionsActionIdDelete(
            path: .init(actionId: actionId),
        )
        switch response {
        case .ok:
            logger.info("Deleted action: \(actionId)")
        case .undocumented(let statusCode, _):
            if statusCode == 403 {
                throw ActionLibraryError.cannotDeleteBuiltin
            }
            throw ActionLibraryError.serverError
        case .unprocessableContent:
            throw ActionLibraryError.serverError
        }
    }

    // MARK: - Usage Tracking

    /// Record that an action was used
    func recordUse(_ actionId: String) async {
        do {
            _ = try await client.api.recordActionUseApiActionsActionIdUsePost(
                path: .init(actionId: actionId),
            )
            logger.debug("Recorded use of action: \(actionId)")
        } catch {
            logger.error("Failed to record action use: \(error.localizedDescription)")
        }
    }

    // MARK: - Import/Export

    /// Export action as JSON
    func exportAction(_ actionId: String) async throws -> String {
        let response = try await client.api.exportActionApiActionsActionIdExportGet(
            path: .init(actionId: actionId),
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.jsonData
        case .unprocessableContent, .undocumented:
            throw ActionLibraryError.serverError
        }
    }

    /// Import action from JSON
    func importAction(_ json: String, newId: Bool = true) async throws -> ActionItem {
        let response = try await client.api.importActionApiActionsImportPost(
            body: .json(.init(jsonData: json, newId: newId))
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json, as: ActionItem.self)
        case .unprocessableContent, .undocumented:
            throw ActionLibraryError.serverError
        }
    }

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

// ActionItem and CreateActionRequest are defined in ActionsService.swift — do not duplicate

// MARK: - Errors

enum ActionLibraryError: LocalizedError {
    case invalidURL
    case serverError
    case cannotDeleteBuiltin

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .serverError:
            return "Server error"
        case .cannotDeleteBuiltin:
            return "Cannot delete built-in action"
        }
    }
}
