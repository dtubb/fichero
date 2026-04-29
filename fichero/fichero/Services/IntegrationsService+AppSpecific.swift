import Foundation

// MARK: - App-Specific Methods

extension IntegrationsService {

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
