import Foundation
import OpenAPIRuntime
import HTTPTypes

/// Middleware that adds the X-Fichero-Library-Path header to requests.
///
/// This replicates the behavior of the legacy APIClient which sends
/// the current library path with each request.
public struct LibraryPathMiddleware: ClientMiddleware {
    /// The library path to send with each request.
    /// Can be updated dynamically.
    public var libraryPath: String?

    /// Endpoints that don't need the library path header
    private let appWideEndpoints = ["/health", "/providers/catalog", "/providers/models"]

    public init(libraryPath: String? = nil) {
        self.libraryPath = libraryPath
    }

    public func intercept(
        _ request: HTTPRequest,
        body: HTTPBody?,
        baseURL: URL,
        operationID: String,
        next: (HTTPRequest, HTTPBody?, URL) async throws -> (HTTPResponse, HTTPBody?)
    ) async throws -> (HTTPResponse, HTTPBody?) {
        var request = request

        // Check if this is an app-wide endpoint
        let path = request.path ?? ""
        let isAppWide = appWideEndpoints.contains { path.contains($0) }

        // Add library path header for library-scoped endpoints
        if !isAppWide, let libraryPath = libraryPath {
            request.headerFields[.init("X-Fichero-Library-Path")!] = libraryPath
        }

        return try await next(request, body, baseURL)
    }
}

/// Actor-safe wrapper for LibraryPathMiddleware that can be shared across tasks.
@MainActor
public final class LibraryPathProvider: ObservableObject {
    @Published public var libraryPath: String?

    public init(libraryPath: String? = nil) {
        self.libraryPath = libraryPath
    }

    /// Creates a middleware configured with the current library path.
    public func createMiddleware() -> LibraryPathMiddleware {
        LibraryPathMiddleware(libraryPath: libraryPath)
    }
}
