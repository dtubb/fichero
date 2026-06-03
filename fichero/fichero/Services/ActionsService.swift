import Foundation
import OSLog

/// Service for interacting with the Action Library
@MainActor
final class ActionsService: ObservableObject {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "ActionsService")

    @Published var actions: [ActionItem] = []
    @Published var categories: [String] = []
    @Published var isLoading = false
    @Published var error: String?

    private let engineBaseURL = "http://localhost:8765"

    private enum Endpoint {
        static let actions = "/api/actions"
        static let builtin = "/api/actions/builtin"
        static let categories = "/api/actions/categories"
        static let category = "/api/actions/category/{category}"
        static let composite = "/api/actions/composite"
        static let custom = "/api/actions/custom"
        static let fromNode = "/api/actions/from-node"
        static let importAction = "/api/actions/import"
        static let popular = "/api/actions/popular"
        static let recent = "/api/actions/recent"
        static let search = "/api/actions/search"
        static let action = "/api/actions/{action_id}"
        static let actionExport = "/api/actions/{action_id}/export"
        static let actionUse = "/api/actions/{action_id}/use"
    }

    /// Build a GET request that carries the engine Bearer token (#742).
    /// All callers used to use `URLSession.shared.data(from: url)`, which
    /// strips headers — that 401s post-#742.
    private func authedGet(_ url: URL) -> URLRequest {
        var request = URLRequest(url: url)
        request.addEngineAuth()
        return request
    }

    private func url(for endpoint: String, replacements: [String: String] = [:]) -> URL? {
        var path = endpoint
        for (placeholder, value) in replacements {
            path = path.replacingOccurrences(of: "{\(placeholder)}", with: value)
        }
        return URL(string: "\(engineBaseURL)\(path)")
    }

    // MARK: - List Actions

    func loadActions() async {
        isLoading = true
        error = nil

        do {
            guard let url = url(for: Endpoint.actions) else { throw ActionsError.invalidURL }
            let (data, _) = try await URLSession.shared.data(for: authedGet(url))
            actions = try JSONDecoder().decode([ActionItem].self, from: data)
            logger.info("Loaded \(self.actions.count) actions")
        } catch {
            self.error = error.localizedDescription
            logger.error("Failed to load actions: \(error.localizedDescription)")
        }

        isLoading = false
    }

    func loadCategories() async {
        do {
            guard let url = url(for: Endpoint.categories) else { return }
            let (data, _) = try await URLSession.shared.data(for: authedGet(url))
            let result = try JSONDecoder().decode(CategoriesResponse.self, from: data)
            categories = result.categories.map { $0.name }
        } catch {
            logger.error("Failed to load categories: \(error.localizedDescription)")
        }
    }

    func loadBuiltinActions() async -> [ActionItem] {
        do {
            guard let url = url(for: Endpoint.builtin) else { return [] }
            let (data, _) = try await URLSession.shared.data(for: authedGet(url))
            return try JSONDecoder().decode([ActionItem].self, from: data)
        } catch {
            return []
        }
    }

    func loadCustomActions() async -> [ActionItem] {
        do {
            guard let url = url(for: Endpoint.custom) else { return [] }
            let (data, _) = try await URLSession.shared.data(for: authedGet(url))
            return try JSONDecoder().decode([ActionItem].self, from: data)
        } catch {
            return []
        }
    }

    func loadActions(category: String) async -> [ActionItem] {
        do {
            guard let url = url(for: Endpoint.category, replacements: ["category": category]) else { return [] }
            let (data, _) = try await URLSession.shared.data(for: authedGet(url))
            return try JSONDecoder().decode([ActionItem].self, from: data)
        } catch {
            return []
        }
    }

    func loadRecentActions(limit: Int = 10) async -> [ActionItem] {
        do {
            guard var components = url(for: Endpoint.recent).flatMap({ URLComponents(url: $0, resolvingAgainstBaseURL: false) })
            else { return [] }
            components.queryItems = [URLQueryItem(name: "limit", value: String(limit))]
            guard let url = components.url else { return [] }
            let (data, _) = try await URLSession.shared.data(for: authedGet(url))
            return try JSONDecoder().decode([ActionItem].self, from: data)
        } catch {
            return []
        }
    }

    func loadPopularActions(limit: Int = 10) async -> [ActionItem] {
        do {
            guard var components = url(for: Endpoint.popular).flatMap({ URLComponents(url: $0, resolvingAgainstBaseURL: false) })
            else { return [] }
            components.queryItems = [URLQueryItem(name: "limit", value: String(limit))]
            guard let url = components.url else { return [] }
            let (data, _) = try await URLSession.shared.data(for: authedGet(url))
            return try JSONDecoder().decode([ActionItem].self, from: data)
        } catch {
            return []
        }
    }

    // MARK: - Search

    func searchActions(query: String?, category: String? = nil, tags: [String]? = nil) async -> [ActionItem] {
        var components = url(for: Endpoint.search).flatMap { URLComponents(url: $0, resolvingAgainstBaseURL: false) }
        var queryItems: [URLQueryItem] = []

        if let query = query, !query.isEmpty {
            queryItems.append(URLQueryItem(name: "query", value: query))
        }
        if let category = category {
            queryItems.append(URLQueryItem(name: "category", value: category))
        }
        if let tags = tags, !tags.isEmpty {
            queryItems.append(URLQueryItem(name: "tags", value: tags.joined(separator: ",")))
        }

        components?.queryItems = queryItems.isEmpty ? nil : queryItems

        do {
            guard let url = components?.url else { return [] }
            let (data, _) = try await URLSession.shared.data(for: authedGet(url))
            return try JSONDecoder().decode([ActionItem].self, from: data)
        } catch {
            return []
        }
    }

    // MARK: - CRUD

    func getAction(id: String) async throws -> ActionItem {
        guard let url = url(for: Endpoint.action, replacements: ["action_id": id]) else { throw ActionsError.invalidURL }
        let (data, _) = try await URLSession.shared.data(for: authedGet(url))
        return try JSONDecoder().decode(ActionItem.self, from: data)
    }

    func createAction(_ request: CreateActionRequest) async throws -> ActionItem {
        guard let url = url(for: Endpoint.actions) else { throw ActionsError.invalidURL }

        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.addEngineAuth()
        urlRequest.httpBody = try JSONEncoder().encode(request)

        let (data, _) = try await URLSession.shared.data(for: urlRequest)
        let action = try JSONDecoder().decode(ActionItem.self, from: data)
        await loadActions()
        return action
    }

    func deleteAction(id: String) async throws {
        guard let url = url(for: Endpoint.action, replacements: ["action_id": id]) else { throw ActionsError.invalidURL }

        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.addEngineAuth()

        let (_, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw ActionsError.deleteFailed
        }

        await loadActions()
    }

    func recordUse(actionId: String) async {
        guard let url = url(for: Endpoint.actionUse, replacements: ["action_id": actionId]) else { return }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addEngineAuth()

        _ = try? await URLSession.shared.data(for: request)
    }

    // MARK: - Import/Export

    func exportAction(id: String) async throws -> String {
        guard let url = url(for: Endpoint.actionExport, replacements: ["action_id": id]) else {
            throw ActionsError.invalidURL
        }
        let (data, _) = try await URLSession.shared.data(for: authedGet(url))
        let result = try JSONDecoder().decode([String: String].self, from: data)
        return result["json"] ?? ""
    }

    func importAction(json: String) async throws -> ActionItem {
        guard let url = url(for: Endpoint.importAction) else { throw ActionsError.invalidURL }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addEngineAuth()

        let body = ["json_data": json, "new_id": true] as [String: Any]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, _) = try await URLSession.shared.data(for: request)
        let action = try JSONDecoder().decode(ActionItem.self, from: data)
        await loadActions()
        return action
    }

    func updateAction(id: String, request: UpdateActionRequest) async throws -> ActionItem {
        guard let url = url(for: Endpoint.action, replacements: ["action_id": id]) else { throw ActionsError.invalidURL }

        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "PUT"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.addEngineAuth()
        urlRequest.httpBody = try JSONEncoder().encode(request)

        let (data, _) = try await URLSession.shared.data(for: urlRequest)
        let action = try JSONDecoder().decode(ActionItem.self, from: data)
        await loadActions()
        return action
    }

    func createActionFromNode(_ request: CreateFromNodeActionRequest) async throws -> ActionItem {
        guard let url = url(for: Endpoint.fromNode) else { throw ActionsError.invalidURL }
        return try await postAction(url: url, body: request)
    }

    func createCompositeAction(_ request: CreateCompositeActionRequest) async throws -> ActionItem {
        guard let url = url(for: Endpoint.composite) else { throw ActionsError.invalidURL }
        return try await postAction(url: url, body: request)
    }

    private func postAction<B: Encodable>(url: URL, body: B) async throws -> ActionItem {
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.addEngineAuth()
        urlRequest.httpBody = try JSONEncoder().encode(body)

        let (data, _) = try await URLSession.shared.data(for: urlRequest)
        let action = try JSONDecoder().decode(ActionItem.self, from: data)
        await loadActions()
        return action
    }
}

// MARK: - Models

struct ActionItem: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let description: String
    let category: String
    let tags: [String]
    let icon: String
    let nodeTemplate: [String: AnyCodable]
    let nodes: [[String: AnyCodable]]
    let edges: [[String: AnyCodable]]
    let isBuiltin: Bool
    let isComposite: Bool
    let author: String
    let useCount: Int
    let lastUsedAt: String?
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id, name, description, category, tags, icon
        case nodeTemplate = "node_template"
        case nodes, edges
        case isBuiltin = "is_builtin"
        case isComposite = "is_composite"
        case author
        case useCount = "use_count"
        case lastUsedAt = "last_used_at"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }

    static func == (lhs: ActionItem, rhs: ActionItem) -> Bool {
        lhs.id == rhs.id
    }
}

// AnyCodable is defined in Models/Document.swift — do not duplicate

struct CreateActionRequest: Encodable {
    let name: String
    var description: String = ""
    var category: String = "custom"
    var tags: [String] = []
    var icon: String = "square.stack.3d.up"
    var nodeTemplate: [String: Any] = [:]
    var nodes: [[String: Any]] = []
    var edges: [[String: Any]] = []
    var author: String = ""

    enum CodingKeys: String, CodingKey {
        case name, description, category, tags, icon
        case nodeTemplate = "node_template"
        case nodes, edges, author
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(name, forKey: .name)
        try container.encode(description, forKey: .description)
        try container.encode(category, forKey: .category)
        try container.encode(tags, forKey: .tags)
        try container.encode(icon, forKey: .icon)
        try container.encode(author, forKey: .author)
    }
}

struct UpdateActionRequest: Encodable {
    var name: String?
    var description: String?
    var category: String?
    var tags: [String]?
    var icon: String?

    enum CodingKeys: String, CodingKey {
        case name, description, category, tags, icon
    }
}

struct CreateFromNodeActionRequest: Encodable {
    let name: String
    let node: [String: AnyCodable]
    var description: String = ""
    var category: String = "custom"
    var tags: [String] = []
}

struct CreateCompositeActionRequest: Encodable {
    let name: String
    let nodes: [[String: AnyCodable]]
    let edges: [[String: AnyCodable]]
    var description: String = ""
    var category: String = "custom"
    var tags: [String] = []
}

struct CategoriesResponse: Codable {
    let categories: [CategoryInfo]
}

struct CategoryInfo: Codable {
    let value: String
    let name: String
}

enum ActionsError: LocalizedError {
    case invalidURL
    case deleteFailed

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL"
        case .deleteFailed: return "Failed to delete action"
        }
    }
}
