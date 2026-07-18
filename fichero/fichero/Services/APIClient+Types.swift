import FicheroAPIClient
import Foundation

// MARK: - Response Types

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

/// The engine auth headers for `url` — `Authorization: Bearer <token>` (#742)
/// and, when given, the per-library `X-Fichero-Library-Path` (#2648/#3076).
///
/// The ONE derivation of those headers. `URLRequest.addEngineAuth` applies them
/// to a request; callers that must hand headers to a framework which does its
/// own networking (AVFoundation's `AVURLAsset`, which range-requests a media
/// stream and cannot be routed through the generated client) take the dictionary
/// directly, instead of building a throwaway `URLRequest` just to read its
/// headers back out.
///
/// Health endpoint never needs auth and is the only one we deliberately skip —
/// see `AuthTokenMiddleware.unauthenticatedPaths`.
func engineAuthHeaders(for url: URL?, libraryPath: String? = nil) -> [String: String] {
    var headers: [String: String] = [:]
    let path = url?.path ?? ""
    // Resolve the token for THIS request's host (#2866), not the global
    // default — raw requests can target any of the backends the app holds.
    //
    // Read the token ONCE, non-blocking (#3948). This is a synchronous helper
    // reachable on the main actor (readiness probe, 5s heartbeat, waitForBackend
    // poll); the old `waitForTokenBlocking` slept up to 3s per call, freezing the
    // main actor every heartbeat when `.api-key` was absent. The outcome is
    // identical either way: if no token is on disk the request goes header-free
    // and 401s — the honest result the probe already classifies as `authRejected`
    // — so blocking only ever added a beachball in front of the same answer.
    if !AuthTokenMiddleware.isUnauthenticatedPath(path),
       let token = AuthTokenMiddleware.readTokenFromDisk(hostString: url?.absoluteString) {
        headers["Authorization"] = "Bearer \(token)"
    }
    if let libraryPath {
        // NFC-normalize before encoding (#3076) so raw-URLSession callsites
        // carry the same canonical bytes as the middleware choke point.
        let normalized = libraryPath.nfcNormalized
        // Percent-encode non-ASCII paths (#2648) so header transport stays
        // lossless. The engine unquotes on read, and pure-ASCII paths are
        // unchanged, so this is a no-op unless encoding is actually needed.
        let encoded = normalized.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? normalized
        headers["X-Fichero-Library-Path"] = encoded
    }
    return headers
}

extension URLRequest {
    /// Attach `Authorization: Bearer <token>` (#742) and, if provided, the
    /// per-library `X-Fichero-Library-Path` header. Use on every raw
    /// URLSession callsite that does not flow through the OpenAPI middleware
    /// (FicheroClient). The caller decides whether a request is library-scoped
    /// by passing `libraryPath` or omitting it — there is no skip-list here;
    /// `LibraryPathMiddleware.isAppWidePath` owns that question for the
    /// generated client.
    mutating func addEngineAuth(libraryPath: String? = nil) {
        for (field, value) in engineAuthHeaders(for: url, libraryPath: libraryPath) {
            setValue(value, forHTTPHeaderField: field)
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
