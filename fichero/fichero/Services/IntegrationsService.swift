import Foundation
import OSLog

/// Service for interacting with app integrations (DEVONthink, Bookends, Tinderbox)
@MainActor
final class IntegrationsService: ObservableObject {
    private let logger = Logger(subsystem: "com.fichero.fichero", category: "IntegrationsService")

    @Published var integrations: [AppIntegration] = []
    @Published var isLoading = false
    @Published var error: String?

    let baseURL = "http://localhost:8765/api/integrations"

    /// GET request with engine Bearer token (#742). Replaces former
    /// `URLSession.shared.data(from: url)` callsites. `internal` so the
    /// `+AppSpecific` extension in another file can use it.
    func authedGet(_ url: URL) -> URLRequest {
        var request = URLRequest(url: url)
        request.addEngineAuth()
        return request
    }

    // MARK: - Integration Management

    /// Load all available integrations
    func loadIntegrations() async {
        isLoading = true
        error = nil

        do {
            guard let url = URL(string: baseURL) else {
                throw IntegrationsError.invalidURL
            }

            let (data, response) = try await URLSession.shared.data(for: authedGet(url))

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
            request.addEngineAuth()

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

        let (data, response) = try await URLSession.shared.data(for: authedGet(url))

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

        let (data, response) = try await URLSession.shared.data(for: authedGet(url))

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
        request.addEngineAuth()

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
        request.addEngineAuth()

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
        request.addEngineAuth()

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw IntegrationsError.serverError
        }

        let result = try JSONDecoder().decode([String: Bool].self, from: data)
        return result["success"] ?? false
    }

}
