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
    @Published public private(set) var baseURL: URL

    /// The OpenAPI API root (`/api`) under `baseURL`.
    public var apiBaseURL: URL { baseURL.appendingPathComponent("api") }

    /// The library path provider (for updating the path dynamically)
    private let libraryPathProvider: LibraryPathProvider

    /// The session the client was configured with (a custom/mock/certificate-pinned
    /// URLSession), retained so `rebuildClient()` — fired on every `currentLibraryPath`
    /// or `baseURL` change — REUSES it instead of silently dropping back to the default
    /// real-network transport. #4024: without this, an injected session was lost the
    /// instant a wrapper (e.g. APIClient) touched the library path, escaping requests to
    /// the real network (the MCP/Schedules/Chain DNS failures).
    private let configuredSession: URLSession?

    /// Current library path - matches legacy APIClient interface
    @Published public var currentLibraryPath: String? {
        didSet {
            libraryPathProvider.libraryPath = currentLibraryPath
            rebuildClient()
        }
    }

    /// Creates a new Fichero API client.
    /// - Parameters:
    ///   - baseURL: The base URL of the Fichero backend (default: localhost:8765 over HTTPS)
    ///   - libraryPath: Optional library path header value
    ///   - session: Optional URL session override, used by callers that need
    ///     a custom transport such as certificate-pinned pairing probes.
    public init(
        baseURL: URL = URL(string: "https://127.0.0.1:8765")!,
        libraryPath: String? = nil,
        session: URLSession? = nil
    ) {
        self.baseURL = baseURL
        self.libraryPathProvider = LibraryPathProvider(libraryPath: libraryPath)
        self.configuredSession = session
        self.currentLibraryPath = libraryPath

        // The API paths in OpenAPI already include /api prefix, so use base URL directly
        // LibraryPathMiddleware injects X-Fichero-Library-Path centrally (#1710).
        // #1710 Phase 2: with the middleware in place, the per-call-site
        // `headers: .init(xFicheroLibraryPath:)` args in the generated services
        // become redundant and can be stripped — see issue #1710 for the sweep.
        self.api = Client(
            serverURL: baseURL,
            configuration: .init(dateTranscoder: LenientISO8601DateTranscoder()),
            transport: Self.makeTransport(session: session),
            middlewares: [
                AuthTokenMiddleware(),
                libraryPathProvider.createMiddleware()
            ]
        )
    }

    /// Convenience initializer for pairing probes that need to pin a specific
    /// host certificate before the remote device is persisted.
    public init(
        baseURL: URL = URL(string: "https://127.0.0.1:8765")!,
        libraryPath: String? = nil,
        expectedSPKIPin: String?
    ) throws {
        self.baseURL = baseURL
        self.libraryPathProvider = LibraryPathProvider(libraryPath: libraryPath)
        self.currentLibraryPath = libraryPath

        let session: URLSession? = if let expectedSPKIPin {
            try RemoteCertificatePinning.pinnedSession(expectedSPKIPin: expectedSPKIPin)
        } else {
            nil
        }
        self.configuredSession = session

        self.api = Client(
            serverURL: baseURL,
            configuration: .init(dateTranscoder: LenientISO8601DateTranscoder()),
            transport: Self.makeTransport(session: session),
            middlewares: [
                AuthTokenMiddleware(),
                libraryPathProvider.createMiddleware()
            ]
        )
    }

    /// Rebuild the client with updated middleware (called when libraryPath changes).
    /// #4024: reuse the originally-configured session so an injected custom/mock/pinned
    /// transport survives library-path / baseURL changes instead of reverting to the
    /// default real-network transport.
    private func rebuildClient() {
        self.api = Client(
            serverURL: baseURL,
            configuration: .init(dateTranscoder: LenientISO8601DateTranscoder()),
            transport: Self.makeTransport(session: configuredSession),
            middlewares: [
                AuthTokenMiddleware(),
                libraryPathProvider.createMiddleware()
            ]
        )
    }

    public func reconfigure(baseURL: URL) {
        guard self.baseURL != baseURL else { return }
        self.baseURL = baseURL
        rebuildClient()
    }

    /// Default client pointing to localhost:8765
    public static var localhost: FicheroClient {
        FicheroClient()
    }

    private static func makeTransport(session: URLSession? = nil) -> URLSessionTransport {
        let configuration = URLSessionConfiguration.default
        let session = session ?? RemoteCertificatePinning.configuredSession(configuration: configuration)
        return URLSessionTransport(configuration: .init(session: session))
    }
}

// MARK: - Type Aliases for Common Types

// Re-export commonly used generated types for convenience
public typealias GeneratedWorkflow = Components.Schemas.WorkflowDef
public typealias GeneratedWorkflowResponse = Components.Schemas.WorkflowResponse
public typealias GeneratedDocument = Components.Schemas.Document
