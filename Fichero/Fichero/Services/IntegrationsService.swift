import Foundation
import OSLog

/// Service for interacting with app integrations (DEVONthink, Bookends, Tinderbox)
@MainActor
final class IntegrationsService: ObservableObject {
    private let logger = Logger(subsystem: "com.fichero.app", category: "IntegrationsService")

    @Published var integrations: [AppIntegration] = []
    @Published var isLoading = false
    @Published var error: String?

    private let baseURL = "http://localhost:8765/api/integrations"

    // MARK: - Integration Management

    /// Load all available integrations
    func loadIntegrations() async {
        isLoading = true
        error = nil

        do {
            guard let url = URL(string: baseURL) else {
                throw IntegrationsError.invalidURL
            }

            let (data, response) = try await URLSession.shared.data(from: url)

            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else {
                throw IntegrationsError.serverError
            }

            let decoder = JSONDecoder()
            integrations = try decoder.decode([AppIntegration].self, from: data)
            logger.info("Loaded \(self.integrations.count) integrations")
        } catch {
            self.error = error.localizedDescription
            logger.error("Failed to load integrations: \(error.localizedDescription)")
        }

        isLoading = false
    }

    /// Refresh a specific integration's status
    func refreshIntegration(_ name: String) async -> AppIntegration? {
        do {
            guard let url = URL(string: "\(baseURL)/\(name.lowercased())/refresh") else {
                throw IntegrationsError.invalidURL
            }

            var request = URLRequest(url: url)
            request.httpMethod = "POST"

            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else {
                throw IntegrationsError.serverError
            }

            let decoder = JSONDecoder()
            let integration = try decoder.decode(AppIntegration.self, from: data)

            // Update in list
            if let index = integrations.firstIndex(where: { $0.name.lowercased() == name.lowercased() }) {
                integrations[index] = integration
            }

            return integration
        } catch {
            logger.error("Failed to refresh \(name): \(error.localizedDescription)")
            return nil
        }
    }

    // MARK: - List Items

    /// List items from an integration
    func listItems(
        from appName: String,
        limit: Int = 100,
        search: String? = nil,
        database: String? = nil,
        container: String? = nil
    ) async throws -> [IntegrationItem] {
        var urlComponents = URLComponents(string: "\(baseURL)/\(appName.lowercased())/items")
        var queryItems: [URLQueryItem] = [
            URLQueryItem(name: "limit", value: String(limit))
        ]

        if let search = search, !search.isEmpty {
            queryItems.append(URLQueryItem(name: "search", value: search))
        }
        if let database = database {
            queryItems.append(URLQueryItem(name: "database", value: database))
        }
        if let container = container {
            queryItems.append(URLQueryItem(name: "container", value: container))
        }

        urlComponents?.queryItems = queryItems

        guard let url = urlComponents?.url else {
            throw IntegrationsError.invalidURL
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw IntegrationsError.serverError
        }

        if httpResponse.statusCode == 503 {
            throw IntegrationsError.appNotAvailable(appName)
        }

        guard httpResponse.statusCode == 200 else {
            throw IntegrationsError.serverError
        }

        let decoder = JSONDecoder()
        return try decoder.decode([IntegrationItem].self, from: data)
    }

    /// Get a specific item
    func getItem(from appName: String, externalId: String) async throws -> IntegrationItem {
        guard let url = URL(string: "\(baseURL)/\(appName.lowercased())/items/\(externalId)") else {
            throw IntegrationsError.invalidURL
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw IntegrationsError.serverError
        }

        let decoder = JSONDecoder()
        return try decoder.decode(IntegrationItem.self, from: data)
    }

    // MARK: - Import/Export

    /// Import an item from an integration
    func importItem(
        from appName: String,
        externalId: String,
        targetPath: String? = nil
    ) async throws -> ImportResult {
        guard let url = URL(string: "\(baseURL)/\(appName.lowercased())/import") else {
            throw IntegrationsError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any?] = [
            "external_id": externalId,
            "target_path": targetPath
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body.compactMapValues { $0 })

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw IntegrationsError.serverError
        }

        let decoder = JSONDecoder()
        return try decoder.decode(ImportResult.self, from: data)
    }

    /// Export a file to an integration
    func exportItem(
        to appName: String,
        filePath: String,
        metadata: [String: String]? = nil,
        database: String? = nil,
        group: String? = nil,
        container: String? = nil,
        prototype: String? = nil
    ) async throws -> ExportResult {
        guard let url = URL(string: "\(baseURL)/\(appName.lowercased())/export") else {
            throw IntegrationsError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any?] = [
            "file_path": filePath,
            "metadata": metadata,
            "database": database,
            "group": group,
            "container": container,
            "prototype": prototype
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body.compactMapValues { $0 })

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw IntegrationsError.serverError
        }

        let decoder = JSONDecoder()
        return try decoder.decode(ExportResult.self, from: data)
    }

    /// Open an item in its native app
    func openItem(in appName: String, externalId: String) async throws -> Bool {
        guard let url = URL(string: "\(baseURL)/\(appName.lowercased())/open/\(externalId)") else {
            throw IntegrationsError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw IntegrationsError.serverError
        }

        let result = try JSONDecoder().decode([String: Bool].self, from: data)
        return result["success"] ?? false
    }

    // MARK: - App-Specific Methods

    /// List DEVONthink databases
    func listDEVONthinkDatabases() async throws -> [DEVONthinkDatabase] {
        guard let url = URL(string: "\(baseURL)/devonthink/databases") else {
            throw IntegrationsError.invalidURL
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw IntegrationsError.serverError
        }

        let result = try JSONDecoder().decode([String: [DEVONthinkDatabase]].self, from: data)
        return result["databases"] ?? []
    }

    /// List Bookends libraries
    func listBookendsLibraries() async throws -> [BookendsLibrary] {
        guard let url = URL(string: "\(baseURL)/bookends/libraries") else {
            throw IntegrationsError.invalidURL
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw IntegrationsError.serverError
        }

        let result = try JSONDecoder().decode([String: [BookendsLibrary]].self, from: data)
        return result["libraries"] ?? []
    }

    /// Get a formatted citation from Bookends
    func getBookendsCitation(externalId: String, style: String = "APA") async throws -> String {
        guard let url = URL(string: "\(baseURL)/bookends/citation/\(externalId)?style=\(style)") else {
            throw IntegrationsError.invalidURL
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw IntegrationsError.serverError
        }

        let result = try JSONDecoder().decode([String: String].self, from: data)
        return result["citation"] ?? ""
    }

    /// List Tinderbox documents
    func listTinderboxDocuments() async throws -> [TinderboxDocument] {
        guard let url = URL(string: "\(baseURL)/tinderbox/documents") else {
            throw IntegrationsError.invalidURL
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw IntegrationsError.serverError
        }

        let result = try JSONDecoder().decode([String: [TinderboxDocument]].self, from: data)
        return result["documents"] ?? []
    }

    /// Create a Tinderbox note
    func createTinderboxNote(
        name: String,
        text: String = "",
        container: String? = nil,
        prototype: String? = nil,
        attributes: [String: String]? = nil
    ) async throws -> String {
        guard let url = URL(string: "\(baseURL)/tinderbox/notes") else {
            throw IntegrationsError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any?] = [
            "name": name,
            "text": text,
            "container": container,
            "prototype": prototype,
            "attributes": attributes
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body.compactMapValues { $0 })

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw IntegrationsError.serverError
        }

        let result = try JSONDecoder().decode([String: String].self, from: data)
        guard let noteId = result["id"] else {
            throw IntegrationsError.createFailed
        }
        return noteId
    }
}

// MARK: - Models

struct AppIntegration: Codable, Identifiable, Hashable {
    let name: String
    let bundleId: String
    let status: String
    let version: String?
    let path: String?
    let error: String?

    var id: String { name }

    var isAvailable: Bool {
        status == "available"
    }

    enum CodingKeys: String, CodingKey {
        case name
        case bundleId = "bundle_id"
        case status
        case version
        case path
        case error
    }

    func hash(into hasher: inout Hasher) {
        hasher.combine(name)
    }

    static func == (lhs: AppIntegration, rhs: AppIntegration) -> Bool {
        lhs.name == rhs.name
    }
}

struct IntegrationItem: Codable, Identifiable {
    let externalId: String
    let name: String
    let sourceApp: String
    let itemType: String
    let filePath: String?
    let url: String?
    let content: String?
    let metadata: [String: String]
    let createdAt: String?
    let modifiedAt: String?

    var id: String { externalId }

    enum CodingKeys: String, CodingKey {
        case externalId = "external_id"
        case name
        case sourceApp = "source_app"
        case itemType = "item_type"
        case filePath = "file_path"
        case url
        case content
        case metadata
        case createdAt = "created_at"
        case modifiedAt = "modified_at"
    }
}

struct ImportResult: Codable {
    let success: Bool
    let filePath: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case success
        case filePath = "file_path"
        case error
    }
}

struct ExportResult: Codable {
    let success: Bool
    let externalId: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case success
        case externalId = "external_id"
        case error
    }
}

struct DEVONthinkDatabase: Codable, Identifiable {
    let name: String
    let uuid: String?
    let path: String?

    var id: String { uuid ?? name }
}

struct BookendsLibrary: Codable, Identifiable {
    let name: String
    let path: String?

    var id: String { path ?? name }
}

struct TinderboxDocument: Codable, Identifiable {
    let name: String
    let path: String?

    var id: String { path ?? name }
}

// MARK: - Errors

enum IntegrationsError: LocalizedError {
    case invalidURL
    case serverError
    case appNotAvailable(String)
    case createFailed

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .serverError:
            return "Server error"
        case .appNotAvailable(let app):
            return "\(app) is not available"
        case .createFailed:
            return "Failed to create item"
        }
    }
}
