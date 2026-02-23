// swiftlint:disable file_length
import Foundation
import OSLog

// Service for interacting with the Action Library backend
@MainActor
// swiftlint:disable:next type_body_length
final class ActionLibraryService: ObservableObject {
    private let logger = Logger(subsystem: "com.fichero.app", category: "ActionLibraryService")

    @Published var actions: [ActionItem] = []
    @Published var categories: [String] = []
    @Published var recentActions: [ActionItem] = []
    @Published var popularActions: [ActionItem] = []
    @Published var isLoading = false
    @Published var error: String?

    private let baseURL = "http://localhost:8765/api/actions"
    private var libraryPath: String = ""

    // MARK: - Configuration

    func setLibraryPath(_ path: String) {
        self.libraryPath = path
    }

    private func request(for url: URL) -> URLRequest {
        var request = URLRequest(url: url)
        if !libraryPath.isEmpty {
            request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
        }
        return request
    }

    // MARK: - List Operations

    /// Load all actions
    func loadActions() async {
        isLoading = true
        error = nil

        do {
            guard let url = URL(string: baseURL) else {
                throw ActionLibraryError.invalidURL
            }

            let request = request(for: url)
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else {
                throw ActionLibraryError.serverError
            }

            let decoder = JSONDecoder()
            actions = try decoder.decode([ActionItem].self, from: data)
            logger.info("Loaded \(self.actions.count) actions")
        } catch {
            self.error = error.localizedDescription
            logger.error("Failed to load actions: \(error.localizedDescription)")
        }

        isLoading = false
    }

    /// Load categories
    func loadCategories() async {
        do {
            guard let url = URL(string: "\(baseURL)/categories") else { return }

            let request = request(for: url)
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else { return }

            let result = try JSONDecoder().decode([String: [String]].self, from: data)
            categories = result["categories"] ?? []
        } catch {
            logger.error("Failed to load categories: \(error.localizedDescription)")
        }
    }

    /// Load actions by category
    func loadActions(category: String) async -> [ActionItem] {
        do {
            guard let url = URL(string: "\(baseURL)/category/\(category)") else {
                return []
            }

            let request = request(for: url)
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else { return [] }

            return try JSONDecoder().decode([ActionItem].self, from: data)
        } catch {
            logger.error("Failed to load category: \(error.localizedDescription)")
            return []
        }
    }

    /// Load built-in actions
    func loadBuiltinActions() async -> [ActionItem] {
        do {
            guard let url = URL(string: "\(baseURL)/builtin") else { return [] }

            let request = request(for: url)
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else { return [] }

            return try JSONDecoder().decode([ActionItem].self, from: data)
        } catch {
            logger.error("Failed to load builtin actions: \(error.localizedDescription)")
            return []
        }
    }

    /// Load custom actions
    func loadCustomActions() async -> [ActionItem] {
        do {
            guard let url = URL(string: "\(baseURL)/custom") else { return [] }

            let request = request(for: url)
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else { return [] }

            return try JSONDecoder().decode([ActionItem].self, from: data)
        } catch {
            logger.error("Failed to load custom actions: \(error.localizedDescription)")
            return []
        }
    }

    /// Load recent actions
    func loadRecentActions(limit: Int = 10) async {
        do {
            guard let url = URL(string: "\(baseURL)/recent?limit=\(limit)") else { return }

            let request = request(for: url)
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else { return }

            recentActions = try JSONDecoder().decode([ActionItem].self, from: data)
        } catch {
            logger.error("Failed to load recent actions: \(error.localizedDescription)")
        }
    }

    /// Load popular actions
    func loadPopularActions(limit: Int = 10) async {
        do {
            guard let url = URL(string: "\(baseURL)/popular?limit=\(limit)") else { return }

            let request = request(for: url)
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else { return }

            popularActions = try JSONDecoder().decode([ActionItem].self, from: data)
        } catch {
            logger.error("Failed to load popular actions: \(error.localizedDescription)")
        }
    }

    // MARK: - Search

    /// Search actions
    func search(query: String? = nil, category: String? = nil, tags: [String]? = nil) async -> [ActionItem] {
        do {
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

            guard let url = components?.url else { return [] }

            let request = request(for: url)
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else { return [] }

            return try JSONDecoder().decode([ActionItem].self, from: data)
        } catch {
            logger.error("Search failed: \(error.localizedDescription)")
            return []
        }
    }

    // MARK: - CRUD

    /// Get action by ID
    func getAction(_ actionId: String) async -> ActionItem? {
        do {
            guard let url = URL(string: "\(baseURL)/\(actionId)") else { return nil }

            let request = request(for: url)
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else { return nil }

            return try JSONDecoder().decode(ActionItem.self, from: data)
        } catch {
            logger.error("Failed to get action: \(error.localizedDescription)")
            return nil
        }
    }

    /// Create a new action
    func createAction(_ action: CreateActionRequest) async throws -> ActionItem {
        guard let url = URL(string: baseURL) else {
            throw ActionLibraryError.invalidURL
        }

        var request = request(for: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(action)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw ActionLibraryError.serverError
        }

        let created = try JSONDecoder().decode(ActionItem.self, from: data)
        logger.info("Created action: \(created.name)")
        return created
    }

    /// Delete an action
    func deleteAction(_ actionId: String) async throws {
        guard let url = URL(string: "\(baseURL)/\(actionId)") else {
            throw ActionLibraryError.invalidURL
        }

        var request = request(for: url)
        request.httpMethod = "DELETE"

        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw ActionLibraryError.serverError
        }

        if httpResponse.statusCode == 403 {
            throw ActionLibraryError.cannotDeleteBuiltin
        }

        if httpResponse.statusCode != 200 {
            throw ActionLibraryError.serverError
        }

        logger.info("Deleted action: \(actionId)")
    }

    // MARK: - Usage Tracking

    /// Record that an action was used
    func recordUse(_ actionId: String) async {
        do {
            guard let url = URL(string: "\(baseURL)/\(actionId)/use") else { return }

            var request = request(for: url)
            request.httpMethod = "POST"

            let (_, _) = try await URLSession.shared.data(for: request)
            logger.debug("Recorded use of action: \(actionId)")
        } catch {
            logger.error("Failed to record action use: \(error.localizedDescription)")
        }
    }

    // MARK: - Import/Export

    /// Export action as JSON
    func exportAction(_ actionId: String) async throws -> String {
        guard let url = URL(string: "\(baseURL)/\(actionId)/export") else {
            throw ActionLibraryError.invalidURL
        }

        let request = request(for: url)
        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw ActionLibraryError.serverError
        }

        let result = try JSONDecoder().decode([String: String].self, from: data)
        return result["json"] ?? ""
    }

    /// Import action from JSON
    func importAction(_ json: String, newId: Bool = true) async throws -> ActionItem {
        guard let url = URL(string: "\(baseURL)/import") else {
            throw ActionLibraryError.invalidURL
        }

        var request = request(for: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body = ImportActionRequest(jsonData: json, newId: newId)
        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw ActionLibraryError.serverError
        }

        return try JSONDecoder().decode(ActionItem.self, from: data)
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
        guard let url = URL(string: "\(baseURL)/from-node") else {
            throw ActionLibraryError.invalidURL
        }

        var request = request(for: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any] = [
            "name": name,
            "node": node,
            "description": description,
            "category": category,
            "tags": tags
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw ActionLibraryError.serverError
        }

        return try JSONDecoder().decode(ActionItem.self, from: data)
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
        guard let url = URL(string: "\(baseURL)/composite") else {
            throw ActionLibraryError.invalidURL
        }

        var request = request(for: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any] = [
            "name": name,
            "nodes": nodes,
            "edges": edges,
            "description": description,
            "category": category,
            "tags": tags
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw ActionLibraryError.serverError
        }

        return try JSONDecoder().decode(ActionItem.self, from: data)
    }
}

// ActionItem and CreateActionRequest are defined in ActionsService.swift — do not duplicate

// MARK: - Models

struct ImportActionRequest: Codable {
    let jsonData: String
    let newId: Bool

    enum CodingKeys: String, CodingKey {
        case jsonData = "json_data"
        case newId = "new_id"
    }
}

// AnyCodable is defined in Models/Document.swift — do not duplicate

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
