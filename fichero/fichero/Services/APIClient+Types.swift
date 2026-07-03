import FicheroAPIClient
import Foundation

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

// MARK: - URLRequest engine-auth helper

extension URLRequest {
    /// Attach `Authorization: Bearer <token>` (#742) and, if provided, the
    /// per-library `X-Fichero-Library-Path` header. Use on every raw
    /// URLSession callsite that does not flow through the OpenAPI middleware
    /// (FicheroClient) or `APIClient.configureRequest`.
    ///
    /// Health endpoint never needs auth and is the only one we deliberately
    /// skip — see `AuthTokenMiddleware.unauthenticatedPaths`.
    mutating func addEngineAuth(libraryPath: String? = nil) {
        let path = url?.path ?? ""
        // Resolve the token for THIS request's host (#2866), not the global
        // default — raw requests can target any of the backends the app holds.
        if !AuthTokenMiddleware.isUnauthenticatedPath(path),
           let token = AuthTokenMiddleware.waitForTokenBlocking(hostString: url?.absoluteString) {
            setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let libraryPath {
            // Percent-encode so non-ASCII paths (diacritics, accented home dirs)
            // survive the latin-1 HTTP header transport (#2648). The engine
            // `unquote`s on read (api/library_header.py); pure-ASCII paths encode
            // to themselves, so this is a no-op for them. `.urlPathAllowed`
            // mirrors `urllib.parse.quote(path, safe="/")`.
            let encoded = libraryPath.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? libraryPath
            setValue(encoded, forHTTPHeaderField: "X-Fichero-Library-Path")
        }
    }
}

func engineEventStreamRequest(
    baseURL: URL,
    pathComponents: [String],
    libraryPath: String? = nil
) -> URLRequest {
    let url = pathComponents.reduce(baseURL) { partialURL, component in
        partialURL.appendingPathComponent(component)
    }
    var request = URLRequest(url: url)
    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
    request.addEngineAuth(libraryPath: libraryPath)
    return request
}
