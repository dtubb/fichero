import Foundation
import OSLog

/// Service for interacting with the Action Library
@MainActor
final class ActionsService: ObservableObject {
    private let logger = Logger(subsystem: "com.fichero.app", category: "ActionsService")

    @Published var actions: [ActionItem] = []
    @Published var categories: [String] = []
    @Published var isLoading = false
    @Published var error: String?

    private let baseURL = "http://localhost:8765/api/actions"

    // MARK: - List Actions

    func loadActions() async {
        isLoading = true
        error = nil

        do {
            guard let url = URL(string: baseURL) else { throw ActionsError.invalidURL }
            let (data, _) = try await URLSession.shared.data(from: url)
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
            guard let url = URL(string: "\(baseURL)/categories") else { return }
            let (data, _) = try await URLSession.shared.data(from: url)
            let result = try JSONDecoder().decode(CategoriesResponse.self, from: data)
            categories = result.categories.map { $0.name }
        } catch {
            logger.error("Failed to load categories: \(error.localizedDescription)")
        }
    }

    func loadBuiltinActions() async -> [ActionItem] {
        do {
            guard let url = URL(string: "\(baseURL)/builtin") else { return [] }
            let (data, _) = try await URLSession.shared.data(from: url)
            return try JSONDecoder().decode([ActionItem].self, from: data)
        } catch {
            return []
        }
    }

    func loadCustomActions() async -> [ActionItem] {
        do {
            guard let url = URL(string: "\(baseURL)/custom") else { return [] }
            let (data, _) = try await URLSession.shared.data(from: url)
            return try JSONDecoder().decode([ActionItem].self, from: data)
        } catch {
            return []
        }
    }

    func loadPopularActions(limit: Int = 10) async -> [ActionItem] {
        do {
            guard let url = URL(string: "\(baseURL)/popular?limit=\(limit)") else { return [] }
            let (data, _) = try await URLSession.shared.data(from: url)
            return try JSONDecoder().decode([ActionItem].self, from: data)
        } catch {
            return []
        }
    }

    // MARK: - Search

    func searchActions(query: String?, category: String? = nil, tags: [String]? = nil) async -> [ActionItem] {
        var components = URLComponents(string: "\(baseURL)/search")
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
            let (data, _) = try await URLSession.shared.data(from: url)
            return try JSONDecoder().decode([ActionItem].self, from: data)
        } catch {
            return []
        }
    }

    // MARK: - CRUD

    func getAction(id: String) async throws -> ActionItem {
        guard let url = URL(string: "\(baseURL)/\(id)") else { throw ActionsError.invalidURL }
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode(ActionItem.self, from: data)
    }

    func createAction(_ request: CreateActionRequest) async throws -> ActionItem {
        guard let url = URL(string: baseURL) else { throw ActionsError.invalidURL }

        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = try JSONEncoder().encode(request)

        let (data, _) = try await URLSession.shared.data(for: urlRequest)
        let action = try JSONDecoder().decode(ActionItem.self, from: data)
        await loadActions()
        return action
    }

    func deleteAction(id: String) async throws {
        guard let url = URL(string: "\(baseURL)/\(id)") else { throw ActionsError.invalidURL }

        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"

        let (_, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw ActionsError.deleteFailed
        }

        await loadActions()
    }

    func recordUse(actionId: String) async {
        guard let url = URL(string: "\(baseURL)/\(actionId)/use") else { return }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"

        _ = try? await URLSession.shared.data(for: request)
    }

    // MARK: - Import/Export

    func exportAction(id: String) async throws -> String {
        guard let url = URL(string: "\(baseURL)/\(id)/export") else { throw ActionsError.invalidURL }
        let (data, _) = try await URLSession.shared.data(from: url)
        let result = try JSONDecoder().decode([String: String].self, from: data)
        return result["json"] ?? ""
    }

    func importAction(json: String) async throws -> ActionItem {
        guard let url = URL(string: "\(baseURL)/import") else { throw ActionsError.invalidURL }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body = ["json_data": json, "new_id": true] as [String: Any]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, _) = try await URLSession.shared.data(for: request)
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

struct AnyCodable: Codable, Hashable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let string = try? container.decode(String.self) {
            value = string
        } else if let int = try? container.decode(Int.self) {
            value = int
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let bool = try? container.decode(Bool.self) {
            value = bool
        } else if let array = try? container.decode([AnyCodable].self) {
            value = array.map { $0.value }
        } else if let dict = try? container.decode([String: AnyCodable].self) {
            value = dict.mapValues { $0.value }
        } else {
            value = NSNull()
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        if let string = value as? String {
            try container.encode(string)
        } else if let int = value as? Int {
            try container.encode(int)
        } else if let double = value as? Double {
            try container.encode(double)
        } else if let bool = value as? Bool {
            try container.encode(bool)
        } else {
            try container.encodeNil()
        }
    }

    func hash(into hasher: inout Hasher) {
        if let string = value as? String {
            hasher.combine(string)
        } else if let int = value as? Int {
            hasher.combine(int)
        }
    }

    static func == (lhs: AnyCodable, rhs: AnyCodable) -> Bool {
        String(describing: lhs.value) == String(describing: rhs.value)
    }
}

struct CreateActionRequest: Codable {
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
