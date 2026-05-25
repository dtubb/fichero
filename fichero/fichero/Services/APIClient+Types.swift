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
        if let token = AuthTokenMiddleware.readTokenFromDisk() {
            setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let libraryPath {
            setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
        }
    }
}
