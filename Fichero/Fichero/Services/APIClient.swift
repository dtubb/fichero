import Foundation
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "APIClient")

/// HTTP client for communicating with the Fichero Python backend.
///
/// Uses Swift concurrency (async/await) for all network operations.
/// The backend runs on localhost:8765 when started with `fichero serve`.
///
/// **Per-Window Instance**: Each DocumentTabView creates its own APIClient instance
/// with its own currentLibraryPath. This ensures operations in one window don't
/// affect other windows operating on different .fichero libraries.
@MainActor
class APIClient: ObservableObject {
    private let baseURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    /// Current library path - set by DocumentTabView when a library is loaded
    /// Sent as "X-Fichero-Library-Path" header with every request
    /// This is the path to the .fichero package document (e.g., "/Users/name/Documents/MyLibrary.fichero")
    @Published var currentLibraryPath: String?

    init() {
        self.baseURL = URL(string: "http://127.0.0.1:8765/api")!

        // Configure session
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 300
        self.session = URLSession(configuration: config)

        // Configure decoder
        self.decoder = JSONDecoder()
        // Don't use convertFromSnakeCase since we have explicit CodingKeys
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let dateString = try container.decode(String.self)

            // Try ISO 8601 with fractional seconds first
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = formatter.date(from: dateString) {
                return date
            }

            // Fall back to standard ISO 8601
            formatter.formatOptions = [.withInternetDateTime]
            if let date = formatter.date(from: dateString) {
                return date
            }

            // Try DateFormatter for dates without timezone (Python's default format)
            let dateFormatter = DateFormatter()
            dateFormatter.locale = Locale(identifier: "en_US_POSIX")
            dateFormatter.timeZone = TimeZone(identifier: "UTC")

            // Format: 2025-12-11T15:47:02.776163 (no timezone)
            dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
            if let date = dateFormatter.date(from: dateString) {
                return date
            }

            // Format: 2025-12-11T15:47:02 (no fractional seconds, no timezone)
            dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
            if let date = dateFormatter.date(from: dateString) {
                return date
            }

            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Cannot decode date: \(dateString)")
        }

        // Configure encoder
        self.encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
    }

    // MARK: - Request Configuration

    /// Add library path header to request if currentLibraryPath is set
    private func configureRequest(_ request: inout URLRequest) {
        if let libraryPath = currentLibraryPath {
            request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
        }
    }

    // MARK: - Health Check

    func healthCheck() async throws -> HealthResponse {
        try await get("/health")
    }

    // MARK: - Generic Methods

    func get<T: Decodable>(_ path: String, query: [String: String]? = nil) async throws -> T {
        var url = baseURL.appendingPathComponent(path)

        if let query = query, !query.isEmpty {
            var components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
            components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
            url = components.url!
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        configureRequest(&request)

        logger.info("GET \(url.absoluteString)")

        do {
            let (data, response) = try await session.data(for: request)
            logger.info("Response received, \(data.count) bytes")
            try validateResponse(response, data: data)
            return try decoder.decode(T.self, from: data)
        } catch {
            logger.error("Error: \(String(describing: error))")
            throw error
        }
    }

    func post<T: Decodable, B: Encodable>(_ path: String, body: B) async throws -> T {
        let url = baseURL.appendingPathComponent(path)

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try encoder.encode(body)
        configureRequest(&request)

        logger.info("POST \(url.absoluteString)")
        if let bodyData = request.httpBody, let bodyString = String(data: bodyData, encoding: .utf8) {
            logger.info("Body: \(bodyString)")
        }

        do {
            let (data, response) = try await session.data(for: request)
            logger.info("Response received, \(data.count) bytes")
            if let responseString = String(data: data, encoding: .utf8)?.prefix(500) {
                logger.info("Response: \(String(responseString))")
            }
            try validateResponse(response, data: data)
            return try decoder.decode(T.self, from: data)
        } catch {
            logger.error("POST Error: \(String(describing: error))")
            throw error
        }
    }

    /// POST without body (for endpoints that take query params only)
    func post<T: Decodable>(_ path: String) async throws -> T {
        let url = baseURL.appendingPathComponent(path)

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        configureRequest(&request)

        logger.info("POST \(url.absoluteString) (no body)")

        do {
            let (data, response) = try await session.data(for: request)
            logger.info("Response received, \(data.count) bytes")
            if let responseString = String(data: data, encoding: .utf8)?.prefix(500) {
                logger.info("Response: \(String(responseString))")
            }
            try validateResponse(response, data: data)
            return try decoder.decode(T.self, from: data)
        } catch {
            logger.error("POST Error: \(String(describing: error))")
            throw error
        }
    }

    func put<T: Decodable, B: Encodable>(_ path: String, body: B) async throws -> T {
        let url = baseURL.appendingPathComponent(path)

        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try encoder.encode(body)
        configureRequest(&request)

        let (data, response) = try await session.data(for: request)
        try validateResponse(response, data: data)
        return try decoder.decode(T.self, from: data)
    }

    /// PUT request with query parameters (no body)
    func put<T: Decodable>(_ path: String, query: [String: String]) async throws -> T {
        var urlComponents = URLComponents(string: baseURL.appendingPathComponent(path).absoluteString)!
        if !query.isEmpty {
            urlComponents.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }

        guard let url = urlComponents.url else {
            throw URLError(.badURL)
        }

        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        configureRequest(&request)

        let (data, response) = try await session.data(for: request)
        try validateResponse(response, data: data)
        return try decoder.decode(T.self, from: data)
    }

    func delete(_ path: String) async throws {
        let url = baseURL.appendingPathComponent(path)

        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        configureRequest(&request)

        let (data, response) = try await session.data(for: request)
        try validateResponse(response, data: data)
    }

    // MARK: - URL Builders (for images)

    func thumbnailURL(for documentId: String) -> URL {
        URL(string: "http://127.0.0.1:8765/api/storage/thumbnail/\(documentId)")!
    }

    func displayURL(for documentId: String) -> URL {
        URL(string: "http://127.0.0.1:8765/api/storage/display/\(documentId)")!
    }

    func sourceURL(for documentId: String) -> URL {
        URL(string: "http://127.0.0.1:8765/api/storage/source/\(documentId)")!
    }

    // MARK: - Response Validation

    private func validateResponse(_ response: URLResponse, data: Data) throws {
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        switch httpResponse.statusCode {
        case 200...299:
            return // Success
        case 204:
            return // No content (success for DELETE)
        case 400:
            throw APIError.badRequest(decodeError(data))
        case 404:
            throw APIError.notFound(decodeError(data))
        case 500...599:
            throw APIError.serverError(decodeError(data))
        default:
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: decodeError(data))
        }
    }

    private func decodeError(_ data: Data) -> String {
        if let errorResponse = try? decoder.decode(ErrorResponse.self, from: data) {
            return errorResponse.detail
        }
        return String(data: data, encoding: .utf8) ?? "Unknown error"
    }
}

// MARK: - HTTP Methods Extension

extension APIClient {
    func patch<T: Decodable, B: Encodable>(_ path: String, body: B) async throws -> T {
        let url = URL(string: "http://127.0.0.1:8765/api")!.appendingPathComponent(path)

        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let encoder = JSONEncoder()
        request.httpBody = try encoder.encode(body)
        configureRequest(&request)

        logger.info("PATCH \(url.absoluteString)")

        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        let session = URLSession(configuration: config)

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? "Unknown"
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }

        let decoder = JSONDecoder()
        return try decoder.decode(T.self, from: data)
    }

    /// POST with body, no response (for endpoints that return empty response)
    func postVoid<B: Encodable>(_ path: String, body: B) async throws {
        let url = baseURL.appendingPathComponent(path)

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try encoder.encode(body)
        configureRequest(&request)

        logger.info("POST \(url.absoluteString) (no response)")

        let (data, response) = try await session.data(for: request)
        logger.info("Response received, \(data.count) bytes")
        try validateResponse(response, data: data)
    }
}

// MARK: - Response Types

// HealthResponse is defined in Document.swift

struct ErrorResponse: Codable {
    let detail: String
}

// MARK: - Errors

enum APIError: LocalizedError {
    case invalidResponse
    case badRequest(String)
    case notFound(String)
    case serverError(String)
    case httpError(statusCode: Int, message: String)
    case connectionFailed

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "Invalid response from server"
        case .badRequest(let message):
            return "Bad request: \(message)"
        case .notFound(let message):
            return "Not found: \(message)"
        case .serverError(let message):
            return "Server error: \(message)"
        case .httpError(let code, let message):
            return "HTTP \(code): \(message)"
        case .connectionFailed:
            return "Failed to connect to backend. Is `fichero serve` running?"
        }
    }
}
