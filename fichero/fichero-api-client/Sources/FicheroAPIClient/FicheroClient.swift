import Foundation
import OpenAPIRuntime
import OpenAPIURLSession

/// Convenience wrapper for the generated Fichero API client.
///
/// Usage:
/// ```swift
/// let fichero = FicheroClient(libraryPath: "/path/to/library.fichero")
///
/// // List workflows
/// let response = try await fichero.api.listWorkflowsApiWorkflowsGet(.init())
/// switch response {
/// case .ok(let ok):
///     let workflows = try ok.body.json
/// case .unprocessableContent(let error):
///     print("Validation error")
/// default:
///     print("Unexpected response")
/// }
/// ```
@MainActor
public final class FicheroClient: ObservableObject {
    /// The generated API client
    public private(set) var api: Client

    /// The base URL of the API server
    public let baseURL: URL

    /// The library path provider (for updating the path dynamically)
    private let libraryPathProvider: LibraryPathProvider

    /// Current library path - matches legacy APIClient interface
    @Published public var currentLibraryPath: String? {
        didSet {
            libraryPathProvider.libraryPath = currentLibraryPath
            rebuildClient()
        }
    }

    /// Creates a new Fichero API client.
    /// - Parameters:
    ///   - baseURL: The base URL of the Fichero backend (default: localhost:8765)
    ///   - libraryPath: Optional library path header value
    public init(baseURL: URL = URL(string: "http://127.0.0.1:8765")!, libraryPath: String? = nil) {
        self.baseURL = baseURL
        self.libraryPathProvider = LibraryPathProvider(libraryPath: libraryPath)
        self.currentLibraryPath = libraryPath

        // The API paths in OpenAPI already include /api prefix, so use base URL directly
        self.api = Client(
            serverURL: baseURL,
            configuration: .init(dateTranscoder: LenientISO8601DateTranscoder()),
            transport: URLSessionTransport(),
            middlewares: [
                AuthTokenMiddleware(),
                libraryPathProvider.createMiddleware(),
            ]
        )
    }

    /// Rebuild the client with updated middleware (called when libraryPath changes)
    private func rebuildClient() {
        self.api = Client(
            serverURL: baseURL,
            configuration: .init(dateTranscoder: LenientISO8601DateTranscoder()),
            transport: URLSessionTransport(),
            middlewares: [
                AuthTokenMiddleware(),
                libraryPathProvider.createMiddleware(),
            ]
        )
    }

    /// Default client pointing to localhost:8765
    public static var localhost: FicheroClient {
        FicheroClient()
    }
}

// MARK: - Type Aliases for Common Types

// Re-export commonly used generated types for convenience
public typealias GeneratedWorkflow = Components.Schemas.WorkflowDef
public typealias GeneratedWorkflowResponse = Components.Schemas.WorkflowResponse
public typealias GeneratedDocument = Components.Schemas.Document
