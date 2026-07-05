import Observation
import FicheroAPIClient
import Foundation
import OpenAPIRuntime

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

/// Container for the generated `FicheroClient` and the app-wide DI object every
/// service is constructed with (`@EnvironmentObject`, `*ServiceGenerated(apiClient:)`).
///
/// As of #3030 the hand-rolled `get/post/put/patch/delete` transport shims are
/// gone — every service now calls generated typed operations via `.api`. What
/// remains is the thin wrapper the app depends on: the generated client, its
/// certificate-pinned authenticated transport, the propagated library path, the
/// health check, and the storage URL builders.
@MainActor
@Observable
class APIClient {
    /// The generated OpenAPI client.
    let client: FicheroClient

    /// Direct access to generated operations.
    var api: Client { client.api }

    /// Backend API base URL (`host` with the `/api` prefix). The storage URL
    /// builders append to this; generated operations use `client.baseURL`
    /// directly because their OpenAPI paths already include `/api`.
    var baseURL: URL { client.apiBaseURL }

    /// Current library path - set by DocumentTabView when a library is loaded.
    /// Propagated to the generated client's `LibraryPathMiddleware` so every
    /// library-scoped request carries `X-Fichero-Library-Path`.
    var currentLibraryPath: String? {
        didSet { client.currentLibraryPath = currentLibraryPath }
    }

    init(baseURL: URL = EngineConfig.host, libraryPath: String? = nil) {
        self.client = FicheroClient(baseURL: baseURL, libraryPath: libraryPath)
        self.currentLibraryPath = libraryPath
    }

    /// Test seam: wrap an already-configured `FicheroClient` (e.g. one bound to a
    /// MockURLProtocol session) so service unit tests can drive the real
    /// response-mapping switch without a live engine. Not used in production.
    init(client: FicheroClient) {
        self.client = client
        self.currentLibraryPath = client.currentLibraryPath
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
}
