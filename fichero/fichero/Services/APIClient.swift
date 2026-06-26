import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "APIClient")

/// Parse a date string from the engine's API in any of the four formats
/// the engine emits (ISO with/without fractional seconds, Python isoformat
/// with/without fractional). Used by hand-written response parsers that
/// don't go through the OpenAPI-generated client's LenientISO8601DateTranscoder.
/// Returns nil on parse failure rather than silently coercing to today.
func parseEngineDate(_ dateString: String) -> Date? {
    let isoFractional = ISO8601DateFormatter()
    isoFractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = isoFractional.date(from: dateString) { return date }

    let isoPlain = ISO8601DateFormatter()
    isoPlain.formatOptions = [.withInternetDateTime]
    if let date = isoPlain.date(from: dateString) { return date }

    let dateFormatter = DateFormatter()
    dateFormatter.locale = Locale(identifier: "en_US_POSIX")
    dateFormatter.timeZone = TimeZone(identifier: "UTC")

    dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
    if let date = dateFormatter.date(from: dateString) { return date }

    dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
    if let date = dateFormatter.date(from: dateString) { return date }

    return nil
}

/// HTTP client for communicating with the Fichero Python backend.
///
/// Wraps the generated `FicheroClient` so calls that have a generated
/// operation flow through the typed OpenAPI client and its shared
/// certificate-pinned, authenticated transport. Generic `get/post/put/patch/delete`
/// helpers remain as compatibility shims for call sites that have not yet
/// migrated to generated operations.
@MainActor
class APIClient: ObservableObject {
    /// The generated OpenAPI client.
    let client: FicheroClient

    /// Direct access to generated operations.
    var api: Client { client.api }

    /// Backend API base URL (`host` with the `/api` prefix). Generic helpers
    /// append paths here; generated operations use `client.baseURL` directly
    /// because their OpenAPI paths already include `/api`.
    var baseURL: URL { client.apiBaseURL }

    /// Current library path - set by DocumentTabView when a library is loaded.
    /// Propagated to the generated client's `LibraryPathMiddleware` so every
    /// library-scoped request carries `X-Fichero-Library-Path`.
    @Published var currentLibraryPath: String? {
        didSet { client.currentLibraryPath = currentLibraryPath }
    }

    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(baseURL: URL = EngineConfig.host, libraryPath: String? = nil) {
        self.client = FicheroClient(baseURL: baseURL, libraryPath: libraryPath)
        self.currentLibraryPath = libraryPath

        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 300
        self.session = RemoteCertificatePinning.configuredSession(configuration: config)

        self.decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let dateString = try container.decode(String.self)

            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = formatter.date(from: dateString) {
                return date
            }

            formatter.formatOptions = [.withInternetDateTime]
            if let date = formatter.date(from: dateString) {
                return date
            }

            let dateFormatter = DateFormatter()
            dateFormatter.locale = Locale(identifier: "en_US_POSIX")
            dateFormatter.timeZone = TimeZone(identifier: "UTC")

            dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
            if let date = dateFormatter.date(from: dateString) {
                return date
            }

            dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
            if let date = dateFormatter.date(from: dateString) {
                return date
            }

            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Cannot decode date: \(dateString)"
            )
        }

        self.encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
    }

    // MARK: - Generated Operations

    /// Health check using the generated OpenAPI operation.
    func healthCheck() async throws -> Components.Schemas.HealthResponse {
        let response = try await client.api.healthCheckApiHealthGet(.init())

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .undocumented(let statusCode, _):
            throw APIError.httpError(statusCode: statusCode, message: "Unexpected health response")
        default:
            throw APIError.invalidResponse
        }
    }

    // MARK: - URL Builders (for images)

    func thumbnailURL(for documentId: String) -> URL {
        baseURL.appendingPathComponent("storage/thumbnail/\(documentId)")
    }

    func displayURL(for documentId: String) -> URL {
        baseURL.appendingPathComponent("storage/display/\(documentId)")
    }

    func sourceURL(for documentId: String) -> URL {
        baseURL.appendingPathComponent("storage/source/\(documentId)")
    }

    // MARK: - Legacy Generic Helpers

    /// Add library path header to request if currentLibraryPath is set.
    /// Skips the header for app-wide endpoints (health, providers, settings, registry).
    /// Auth is applied via `URLRequest.addEngineAuth`.
    private func configureRequest(_ request: inout URLRequest) {
        let path = request.url?.path ?? ""
        let isAppWide = LibraryPathMiddleware.isAppWidePath(path)

        if !isAppWide, currentLibraryPath == nil {
            logger.warning("Request to \(path) requires library path but currentLibraryPath is nil")
        }

        request.addEngineAuth(libraryPath: isAppWide ? nil : currentLibraryPath)
    }

    func get<T: Decodable>(_ path: String, query: [String: String]? = nil) async throws -> T {
        var pathOnly = path
        var mergedQuery: [String: String] = query ?? [:]

        if let queryStart = path.firstIndex(of: "?") {
            pathOnly = String(path[..<queryStart])
            let queryString = String(path[path.index(after: queryStart)...])
            for param in queryString.split(separator: "&") {
                let parts = param.split(separator: "=", maxSplits: 1)
                if parts.count == 2 {
                    let key = String(parts[0])
                    let value = String(parts[1])
                    if mergedQuery[key] == nil {
                        mergedQuery[key] = value
                    }
                }
            }
        }

        var components = URLComponents(url: baseURL.appendingPathComponent(pathOnly), resolvingAgainstBaseURL: false)!
        if !mergedQuery.isEmpty {
            components.queryItems = mergedQuery.map { URLQueryItem(name: $0.key, value: $0.value) }
        }

        guard let url = components.url else {
            throw APIError.invalidResponse
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

        do {
            let (data, response) = try await session.data(for: request)
            logger.info("Response received, \(data.count) bytes")
            try validateResponse(response, data: data)
            return try decoder.decode(T.self, from: data)
        } catch {
            logger.error("POST Error: \(String(describing: error))")
            throw error
        }
    }

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
            try validateResponse(response, data: data)
            return try decoder.decode(T.self, from: data)
        } catch {
            logger.error("POST Error: \(String(describing: error))")
            throw error
        }
    }

    func post<T: Decodable>(_ path: String, query: [String: String]) async throws -> T {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty {
            components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }

        guard let url = components.url else {
            throw APIError.invalidResponse
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        configureRequest(&request)

        logger.info("POST \(url.absoluteString) (query only)")

        do {
            let (data, response) = try await session.data(for: request)
            logger.info("Response received, \(data.count) bytes")
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

    // MARK: - Response Validation

    private func validateResponse(_ response: URLResponse, data: Data) throws {
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        switch httpResponse.statusCode {
        case 200...299:
            return
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
        let url = baseURL.appendingPathComponent(path)

        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try encoder.encode(body)
        configureRequest(&request)

        logger.info("PATCH \(url.absoluteString)")

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? "Unknown"
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: message)
        }

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

        logger.info("POST \(url.absoluteString) (void response)")

        let (data, response) = try await session.data(for: request)
        logger.debug("Response received, \(data.count) bytes")
        try validateResponse(response, data: data)
    }
}
