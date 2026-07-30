import AsyncHTTPClient
import Foundation
import NIOPosix
import OpenAPIRuntime
import OpenAPIURLSession
import OpenAPIAsyncHTTPClient

/// Which underlying `ClientTransport` a `FicheroClient` dials the engine with.
///
/// This is a **per-instance** choice (not app-global): a single app may run
/// several `FicheroClient`s concurrently with different modes — e.g. a local
/// library over `.uds` and a remote-shared library over `.https` at the same
/// time. The default is `.https`, preserving the existing URLSession behavior.
public enum TransportMode: Sendable, Equatable {
    /// Default: HTTPS over URLSession (certificate-pinned where configured).
    case https
    /// Plain HTTP/1.1 over an AF_UNIX socket at `path`. TLS is intentionally
    /// absent — the engine exempts the UDS path and grants loopback-owner auth
    /// via a transport marker on the socket (engine "Lane E").
    case uds(path: String)
    #if os(macOS)
    /// In-process: drive the Python engine's ASGI app directly via PythonKit —
    /// no subprocess, no socket, no HTTP server (macOS only; iOS can't embed
    /// CPython). The engine grants loopback-owner auth via the `inmemory`
    /// transport marker (mirrors `.uds`). See `Sources/.../InMemory`.
    case inMemory
    #endif
}

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
    /// `internal` (not `private`) so `FicheroClientTests` can assert the
    /// pinning seam: a client built with `expectedSPKIPin` must hold the
    /// explicitly-pinned session (the KG pane's old availability gate was
    /// removed on the strength of this enforcement living HERE).
    let configuredSession: URLSession?

    /// Which transport this instance dials with (per-instance, default `.https`).
    /// Retained so `rebuildClient()` selects the same transport on every
    /// library-path / baseURL change. `internal` (not `private`) so the streaming
    /// extension can pick the matching server URL for `.uds` vs `.https`.
    let transportMode: TransportMode

    /// The concrete `ClientTransport` the generated `Client` dials with
    /// (URLSession for `.https`, AsyncHTTPClient for `.uds`). Built once and
    /// reused across `rebuildClient()` — and, crucially, reused by the SSE
    /// streaming helper (`streamLines`) so live streams flow through the SAME
    /// transport as every generated call. That is what lets SSE work over a
    /// UDS-only or socket-less engine, where a raw `URLSession` to
    /// `127.0.0.1:8765` would fail. `internal` so the streaming extension can
    /// reach it.
    let transport: any ClientTransport

    /// The transport long-lived SSE subscriptions dial with (#4349).
    ///
    /// SEPARATE from ``transport`` on purpose: streams and requests have
    /// opposite lifetimes (a request holds a connection for milliseconds, a
    /// stream for as long as the library is open) and stream count grows with
    /// the number of open libraries. Sharing one connection pool between them
    /// meant that past a handful of open libraries the streams pinned every
    /// connection and ordinary request traffic queued until it timed out. With
    /// two pools, streams can never starve request traffic no matter how many
    /// libraries are open. See ``LocalTransportPool``.
    ///
    /// `internal` so the streaming extension can reach it.
    let streamTransport: any ClientTransport

    /// The auth + library-path middleware stack the generated `Client` runs.
    /// Both middlewares read their state LIVE per request, so a single instance
    /// stays correct across library-path / baseURL changes and can be reused by
    /// `streamLines` — the streaming request then carries identical auth and
    /// library-scoping headers with nothing hand-rolled.
    let middlewares: [any ClientMiddleware]

    /// Current library path - matches legacy APIClient interface
    @Published public var currentLibraryPath: String? {
        didSet {
            libraryPathProvider.libraryPath = currentLibraryPath
            rebuildClient()
        }
    }

    /// Creates a new Fichero API client.
    /// - Parameters:
    ///   - baseURL: The base URL of the Fichero backend (defaults to local HTTPS for explicit callers).
    ///   - libraryPath: Optional library path header value
    ///   - session: Optional URL session override, used by callers that need
    ///     a custom transport such as certificate-pinned pairing probes.
    ///   - transportMode: Which transport to dial with (per-instance; default
    ///     `.https`). Pass `.uds(path:)` to reach a local engine over an AF_UNIX
    ///     socket instead of HTTPS.
    public init(
        baseURL: URL = URL(string: "https://127.0.0.1:8765")!,
        libraryPath: String? = nil,
        session: URLSession? = nil,
        transportMode: TransportMode = .https
    ) {
        self.baseURL = baseURL
        self.libraryPathProvider = LibraryPathProvider(libraryPath: libraryPath)
        self.configuredSession = session
        self.transportMode = transportMode
        self.currentLibraryPath = libraryPath

        // The API paths in OpenAPI already include /api prefix, so use base URL directly
        // LibraryPathMiddleware injects X-Fichero-Library-Path centrally (#1710).
        // #1710 Phase 2: with the middleware in place, the per-call-site
        // `headers: .init(xFicheroLibraryPath:)` args in the generated services
        // become redundant and can be stripped — see issue #1710 for the sweep.
        let transport = Self.makeTransport(session: session, transportMode: transportMode)
        let middlewares: [any ClientMiddleware] = [
            AuthTokenMiddleware(),
            libraryPathProvider.createMiddleware()
        ]
        self.transport = transport
        self.streamTransport = Self.makeTransport(
            session: session, transportMode: transportMode, usage: .stream
        )
        self.middlewares = middlewares
        self.api = Client(
            serverURL: Self.makeServerURL(baseURL: baseURL, transportMode: transportMode),
            configuration: .init(dateTranscoder: LenientISO8601DateTranscoder()),
            transport: transport,
            middlewares: middlewares
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
        // Certificate pinning is inherently an HTTPS concern, so this initializer
        // is always `.https`.
        self.transportMode = .https
        self.currentLibraryPath = libraryPath

        let session: URLSession? = if let expectedSPKIPin {
            try RemoteCertificatePinning.pinnedSession(expectedSPKIPin: expectedSPKIPin)
        } else {
            nil
        }
        self.configuredSession = session

        let transport = Self.makeTransport(session: session, transportMode: .https)
        let middlewares: [any ClientMiddleware] = [
            AuthTokenMiddleware(),
            libraryPathProvider.createMiddleware()
        ]
        self.transport = transport
        self.streamTransport = Self.makeTransport(
            session: session, transportMode: .https, usage: .stream
        )
        self.middlewares = middlewares
        self.api = Client(
            serverURL: baseURL,
            configuration: .init(dateTranscoder: LenientISO8601DateTranscoder()),
            transport: transport,
            middlewares: middlewares
        )
    }

    /// Rebuild the client with updated middleware (called when libraryPath changes).
    /// #4024: reuse the originally-configured session so an injected custom/mock/pinned
    /// transport survives library-path / baseURL changes instead of reverting to the
    /// default real-network transport.
    private func rebuildClient() {
        self.api = Client(
            serverURL: Self.makeServerURL(baseURL: baseURL, transportMode: transportMode),
            configuration: .init(dateTranscoder: LenientISO8601DateTranscoder()),
            transport: transport,
            middlewares: middlewares
        )
    }

    public func reconfigure(baseURL: URL) {
        guard self.baseURL != baseURL else { return }
        self.baseURL = baseURL
        rebuildClient()
    }

    /// Process-wide `HTTPClient` for the `.uds` transport, pinned to a **NIOPosix**
    /// (BSD-sockets) event loop. AsyncHTTPClient's default `HTTPClient.shared` uses
    /// `NIOTSEventLoopGroup` (Network.framework) on macOS, whose AF_UNIX
    /// `NWConnection` flows intermittently fail to establish under Xcode's debug
    /// launch (the readiness-gate hang this fixes). `MultiThreadedEventLoopGroup`'s
    /// process-lifetime `.singleton` means this client never needs an explicit
    /// shutdown. `internal` so `TransportModeTests` can assert the loop is NIOPosix.
    /// Explicit connection-pool ceiling (#4349): AsyncHTTPClient's inherited
    /// default of 8 per host is a remote-HTTP politeness number that makes no
    /// sense for a local AF_UNIX socket to our own single-tenant engine. See
    /// ``LocalTransportPool`` for the sizing rationale and the measured
    /// server-side ceiling.
    static let udsHTTPClient = HTTPClient(
        eventLoopGroupProvider: .shared(MultiThreadedEventLoopGroup.singleton),
        configuration: LocalTransportPool.configuration(
            softLimit: LocalTransportPool.requestConnectionCeiling
        )
    )

    /// The SEPARATE process-wide `HTTPClient` that long-lived SSE subscriptions
    /// dial over `.uds` (#4349). Same NIOPosix event-loop group (same reasons as
    /// ``udsHTTPClient``), but its OWN connection pool — which is the whole
    /// point: a stream parked on a connection for the lifetime of an open
    /// library can no longer consume request capacity.
    static let udsStreamHTTPClient = HTTPClient(
        eventLoopGroupProvider: .shared(MultiThreadedEventLoopGroup.singleton),
        configuration: LocalTransportPool.configuration(
            softLimit: LocalTransportPool.streamConnectionCeiling
        )
    )

    /// Which population of traffic a transport serves. The two have opposite
    /// lifetimes and therefore get separate connection pools (#4349).
    enum TransportUsage: Sendable {
        /// Short request/response calls (the generated client, `requestData`).
        case request
        /// Long-lived SSE subscriptions (`streamLines`).
        case stream
    }

    /// The URLSession backing `.https` streams. Separate from the request
    /// session so a long-lived SSE body cannot consume URLSession's per-host
    /// connection budget either (`httpMaximumConnectionsPerHost` defaults to 6
    /// on macOS — the same shape of bug as the AsyncHTTPClient pool).
    private static let httpsStreamSession: URLSession = RemoteCertificatePinning.configuredSession(
        configuration: LocalTransportPool.urlSessionConfiguration(
            maximumConnectionsPerHost: LocalTransportPool.streamConnectionCeiling
        )
    )

    /// Unwrap the pool-accounting decorator, if present, to reach the concrete
    /// transport underneath. Lets callers (and the transport-selection tests)
    /// reason about which transport was actually selected without caring that
    /// it is wrapped for pressure accounting.
    /// `nonisolated` because this touches no isolated state — it is a cast plus
    /// a read of `PoolMonitoringTransport.wrapped`, an immutable `let`. Without
    /// it the declaration inherits the type's `@MainActor`, every caller becomes
    /// implicitly async, and the transport tests that call it synchronously stop
    /// compiling — for no safety gained.
    nonisolated static func underlyingTransport(_ transport: any ClientTransport) -> any ClientTransport {
        (transport as? PoolMonitoringTransport)?.wrapped ?? transport
    }

    /// Build the transport for a given mode and usage. Pure helper — no
    /// per-instance state — so concurrent `FicheroClient`s can use different
    /// transports. `internal` (not `private`) so the transport-selection unit
    /// tests can assert the chosen concrete type.
    nonisolated static func makeTransport(
        session: URLSession? = nil,
        transportMode: TransportMode = .https,
        usage: TransportUsage = .request
    ) -> any ClientTransport {
        switch transportMode {
        case .https:
            // Unchanged behavior: HTTPS over URLSession (pinned where configured).
            // An explicitly-injected session (mock / certificate-pinned pairing
            // probe) is honoured for BOTH usages — segmenting it would silently
            // drop the injection, which is exactly the #4024 bug.
            if let session {
                return URLSessionTransport(configuration: .init(session: session))
            }
            let session = usage == .stream
                ? httpsStreamSession
                : RemoteCertificatePinning.configuredSession(
                    configuration: LocalTransportPool.urlSessionConfiguration(
                        maximumConnectionsPerHost: LocalTransportPool.requestConnectionCeiling
                    )
                )
            return URLSessionTransport(configuration: .init(session: session))
        case .uds:
            // Plain HTTP/1.1 over the AF_UNIX socket (path carried in the
            // `http+unix://` authority — see `makeServerURL`). Dial over a
            // NIOPosix (BSD-sockets) HTTPClient, NOT AsyncHTTPClient's default
            // `HTTPClient.shared`: on macOS `.shared` runs on `NIOTSEventLoopGroup`
            // (Network.framework `NWConnection`), whose AF_UNIX flows intermittently
            // fail to establish under Xcode's debug launch (LLDB + preview-dylib
            // injection + contended startup) — "nw_endpoint_flow_failed … / no local
            // endpoint" — which hangs the readiness gate. NIOPosix does a plain POSIX
            // connect(), identical to `curl --unix-socket` and the Python engine.
            //
            // #4349: streams dial a SECOND client with its own pool, and both are
            // wrapped in pool-pressure accounting so a connection leak announces
            // itself with a warning long before the pool runs dry.
            //
            // #4379: `timeout:` is passed EXPLICITLY. Omitting it inherited the
            // transport's one-minute default, which deadlines the whole request
            // *including the response body* — so every SSE subscription died at
            // 60s with `HTTPClientError.deadlineExceeded` ("Lost connection to
            // the Fichero server…"), and a workflow run could not outlive a
            // minute. Requests keep a bounded deadline; streams get one scoped
            // to what a stream actually is. See `LocalTransportPool.deadline`.
            let client = usage == .stream ? udsStreamHTTPClient : udsHTTPClient
            return PoolMonitoringTransport(
                wrapped: AsyncHTTPClientTransport(
                    configuration: .init(
                        client: client,
                        timeout: LocalTransportPool.deadline(for: usage)
                    )
                ),
                pressure: usage == .stream
                    ? LocalTransportPool.streamPressure
                    : LocalTransportPool.requestPressure
            )
        #if os(macOS)
        case .inMemory:
            // Drive the engine's ASGI app in-process. `InMemoryEngineApp.shared()`
            // boots CPython once (env-driven paths, fail-loud) and imports the
            // FastAPI app; the transport ignores host/port on the server URL.
            return InMemoryASGIClientTransport(app: InMemoryEngineApp.shared())
        #endif
        }
    }

    /// The server URL the generated `Client` is pointed at for a given mode.
    ///
    /// For `.https` this is `baseURL` unchanged. For `.uds` the AF_UNIX socket
    /// path is encoded into the authority of an `http+unix://` URL, which
    /// AsyncHTTPClient understands (see `Scheme.httpUnix`). The path is left
    /// empty so the transport appends the operation path (`/api/...`) cleanly.
    ///
    /// The host encoding mirrors AsyncHTTPClient's own
    /// `URL(httpURLWithSocketPath:)` (percent-encodes everything outside its
    /// URL-host-allowed byte set, so `/` becomes `%2F`).
    static func makeServerURL(baseURL: URL, transportMode: TransportMode) -> URL {
        switch transportMode {
        case .https:
            return baseURL
        #if os(macOS)
        case .inMemory:
            // The in-process transport ignores host/port entirely; use a stable
            // placeholder so the generated client appends `/api/...` cleanly.
            return URL(string: "http://asgi.local")!
        #endif
        case .uds(let path):
            // Fail LOUD, not silent: silently returning the HTTPS `baseURL` here
            // would route UDS-intended traffic to the network endpoint — a
            // confusing, hard-to-debug mis-send. Both a non-encodable path
            // (`addingPercentEncoding` → nil) and an unparseable URL are genuine
            // programmer errors (a percent-encoded filesystem path always parses),
            // so trap with a clear message rather than the old `?? path` /
            // baseURL fallbacks (review WARN-1).
            guard let host = path.addingPercentEncoding(withAllowedCharacters: Self.udsHostAllowed),
                  let url = URL(string: "http+unix://\(host)") else {
                preconditionFailure("UDS socket path is not URL-encodable: \(path)")
            }
            return url
        }
    }

    /// Byte set AsyncHTTPClient treats as URL-host-allowed (from its
    /// `addingPercentEncodingAllowingURLHost`). Everything else — notably `/` —
    /// is percent-encoded, placing the socket path in the URL authority.
    private static let udsHostAllowed: CharacterSet = {
        var set = CharacterSet.alphanumerics
        set.insert(charactersIn: "!$&'()*+,-.;=_~")
        return set
    }()
}

// MARK: - Type Aliases for Common Types

// Re-export commonly used generated types for convenience
public typealias GeneratedWorkflow = Components.Schemas.WorkflowDef
public typealias GeneratedWorkflowResponse = Components.Schemas.WorkflowResponse
public typealias GeneratedDocument = Components.Schemas.Document
