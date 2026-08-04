#if os(macOS)
import XCTest
import Foundation
import HTTPTypes
import OpenAPIRuntime
import OpenAPIURLSession
import OpenAPIAsyncHTTPClient
import AsyncHTTPClient
@testable import FicheroAPIClient

/// Transport-agnostic routing test matrix (#4053). Exercises the SAME three
/// endpoints (public health, authenticated model-profiles, streaming
/// changes/stream) through EVERY transport shape via ONE seam —
/// `ClientTransport.send(request, body, baseURL, operationID)` — so a
/// routing / auth / transport-marker regression is caught regardless of which
/// transport ships.
///
/// Transport shapes in the matrix:
///  - `.inMemory`         — real engine in-process, `inmemory` marker.
///  - **UDS-via-in-memory** — real engine in-process with the `fichero.transport
///    = "uds"` marker stamped on the ASGI scope. This is the "test UDS via the
///    python-kit / in-memory load" case the user asked about: it binds NO real
///    socket, yet exercises the engine's UDS-marker loopback-trust path
///    in-process. The marker-override wrapper app re-stamps `scope` before the
///    engine's auth middleware sees it, exactly as `UDSTransportApp` would on a
///    real socket.
///  - `.https` (live)     — real engine over HTTPS. Skip unless
///    `FICHERO_TEST_HTTPS_URL` is set (manager runs against a live engine).
///  - `.uds` (live)       — real engine over an AF_UNIX socket. Skip unless
///    `FICHERO_TEST_UDS_PATH` is set.
///
/// The in-process cases (in-memory + UDS-via-in-memory) are fully runnable
/// headless under `swift test` — no socket, no server. They are the regression
/// guard for the loopback-trust path on BOTH markers.
///
/// Auth is driven explicitly (a `Bearer` header on the raw request) so the
/// matrix tests routing + marker handling in isolation, not the Swift
/// `AuthTokenMiddleware` token-file plumbing (that's covered separately).
@MainActor
final class TransportRoutingMatrixTests: XCTestCase {

    override func setUp() async throws {
        try InMemoryTestEnv.configureOrSkip()
    }

    // MARK: - The one seam

    /// Issue a GET through any `ClientTransport` and return (status, body bytes,
    /// first-line-of-stream-if-any). This is the single transport-agnostic seam
    /// every matrix case funnels through.
    private func sendGet(
        transport: any ClientTransport,
        baseURL: URL,
        path: String,
        headers: [(String, String)] = []
    ) async throws -> (status: Int, body: Data) {
        var request = HTTPRequest(method: .get, scheme: nil, authority: nil, path: path)
        for (k, v) in headers {
            if let name = HTTPField.Name(k) { request.headerFields[name] = v }
        }
        let (response, body) = try await transport.send(
            request, body: nil, baseURL: baseURL, operationID: "matrix.\(path)")
        var bytes = Data()
        if let body { for try await chunk in body { bytes.append(contentsOf: chunk) } }
        return (response.status.code, bytes)
    }

    /// Like `sendGet` but returns the status + the first text line of the
    /// streaming body, then cancels the stream. For SSE endpoints that hold the
    /// connection open (`/api/changes/stream` emits `: connected\n\n` then
    /// keepalives), reading exactly one line proves the route is wired and the
    /// stream opens — without waiting on a real change event.
    private func sendGetFirstLine(
        transport: any ClientTransport,
        baseURL: URL,
        path: String,
        headers: [(String, String)] = []
    ) async throws -> (status: Int, firstLine: String?) {
        var request = HTTPRequest(method: .get, scheme: nil, authority: nil, path: path)
        for (k, v) in headers {
            if let name = HTTPField.Name(k) { request.headerFields[name] = v }
        }
        request.headerFields[.accept] = "text/event-stream"
        let (response, body) = try await transport.send(
            request, body: nil, baseURL: baseURL, operationID: "matrix.stream.\(path)")
        guard let body else { return (response.status.code, nil) }
        // Read byte-by-byte until the first newline (SSE frames are \n-delimited).
        var line: [UInt8] = []
        var firstLine: String?
        for try await chunk in body {
            for byte in chunk {
                if byte == 0x0A {
                    firstLine = String(decoding: line, as: UTF8.self)
                        .trimmingCharacters(in: CharacterSet(charactersIn: "\r"))
                    return (response.status.code, firstLine)
                }
                line.append(byte)
            }
        }
        return (response.status.code, String(decoding: line, as: UTF8.self))
    }

    // MARK: - Transports under test

    /// The real engine app driven in-process (the `inmemory` marker is stamped
    /// by `AsgiBridge.make_scope`).
    private func inMemoryTransport() -> any ClientTransport {
        InMemoryASGIClientTransport(app: InMemoryEngineApp.shared())
    }

    /// A wrapper around the real engine app that overrides the transport marker
    /// to `"uds"` before the engine's auth middleware sees the scope. This is
    /// the "UDS via the python-kit load" transport: no socket is bound, but the
    /// engine exercises the exact UDS-marker loopback-trust path. The wrapper
    /// mirrors `fichero_server.api.uds_transport.UDSTransportApp` on a real socket.
    private func udsMarkerInMemoryTransport() -> any ClientTransport {
        let code = #"""
        from fichero_server.api.main import app as _real

        async def app(scope, receive, send):
            # Re-stamp the UDS marker, exactly as UDSTransportApp does on a real
            # socket. This overrides the "inmemory" marker AsgiBridge.make_scope
            # set, so the engine's _is_loopback_request sees "uds".
            scope["fichero.transport"] = "uds"
            await _real(scope, receive, send)
        """#
        let app = ASGIAppLoader.execApp(code, attribute: "app")
        return InMemoryASGIClientTransport(app: app)
    }

    private let inMemoryBaseURL = URL(string: "http://asgi.local")!

    /// Isolated HOME + known bootstrap token for in-process auth. Set once per
    /// test that needs auth; the engine reads `.api-key` fresh per request.
    /// Callers must also gate on `requireIsolatedBasePath()` so `app.duckdb`
    /// is isolated (frozen at storage import from `FICHERO_BASE_PATH`).
    private func isolatedToken() throws -> (token: String, restore: () -> Void) {
        try InMemoryTestEnv.requireIsolatedBasePath()
        let (_, token, restore) = try InMemoryTestEnv.isolatedHomeWithBootstrapToken()
        return (token, restore)
    }

    // MARK: - Matrix: health (public, unary)

    func testMatrixInMemoryHealth() async throws {
        let (status, body) = try await sendGet(
            transport: inMemoryTransport(), baseURL: inMemoryBaseURL, path: "/api/health")
        XCTAssertEqual(status, 200)
        XCTAssertTrue(String(decoding: body, as: UTF8.self).contains("\"status\":\"healthy\""))
    }

    func testMatrixUDSMarkerInMemoryHealth() async throws {
        // UDS-shaped request through the in-memory app: the engine grants
        // loopback on the "uds" marker (no socket bound).
        let (status, body) = try await sendGet(
            transport: udsMarkerInMemoryTransport(), baseURL: inMemoryBaseURL, path: "/api/health")
        XCTAssertEqual(status, 200)
        XCTAssertTrue(String(decoding: body, as: UTF8.self).contains("\"status\":\"healthy\""))
    }

    func testMatrixHTTPSHealth() async throws {
        let baseURL = try liveHTTPSBaseURL()
        let transport = FicheroClient.liveTransport(transportMode: .https)
        let (status, body) = try await sendGet(transport: transport, baseURL: baseURL, path: "/api/health")
        XCTAssertEqual(status, 200)
        XCTAssertTrue(String(decoding: body, as: UTF8.self).contains("\"status\":\"healthy\""))
    }

    func testMatrixUDSHealth() async throws {
        let socket = try liveUDSPath()
        let baseURL = FicheroClient.makeServerURL(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            transportMode: .uds(path: socket))
        let transport = FicheroClient.liveTransport(transportMode: .uds(path: socket))
        let (status, body) = try await sendGet(transport: transport, baseURL: baseURL, path: "/api/health")
        XCTAssertEqual(status, 200)
        XCTAssertTrue(String(decoding: body, as: UTF8.self).contains("\"status\":\"healthy\""))
    }

    // MARK: - Matrix: authenticated (model-profiles)

    func testMatrixInMemoryAuthenticated() async throws {
        let (token, restore) = try isolatedToken()
        defer { restore() }
        // Without a token: not 200 (proves the endpoint is gated for the inmemory marker).
        let (unauth, _) = try await sendGet(
            transport: inMemoryTransport(), baseURL: inMemoryBaseURL,
            path: "/api/settings/model-profiles")
        XCTAssertNotEqual(unauth, 200, "inmemory: unauthenticated must not be 200 (got \(unauth))")
        // With the bootstrap token + the inmemory marker: 200.
        let (status, body) = try await sendGet(
            transport: inMemoryTransport(), baseURL: inMemoryBaseURL,
            path: "/api/settings/model-profiles",
            headers: [("authorization", "Bearer \(token)")])
        XCTAssertEqual(status, 200, "inmemory: authenticated must be 200, got \(status): \(String(decoding: body, as: UTF8.self))")
    }

    func testMatrixUDSMarkerInMemoryAuthenticated() async throws {
        // THE KEY CASE: UDS-shaped request through the in-memory app. The
        // engine's auth sees the "uds" marker and grants loopback-owner; the
        // bootstrap token validates against the isolated .api-key. Binds no
        // socket — this is "test UDS via the python-kit / in-memory load".
        let (token, restore) = try isolatedToken()
        defer { restore() }
        let (unauth, _) = try await sendGet(
            transport: udsMarkerInMemoryTransport(), baseURL: inMemoryBaseURL,
            path: "/api/settings/model-profiles")
        XCTAssertNotEqual(unauth, 200, "uds-via-inmemory: unauthenticated must not be 200 (got \(unauth))")
        let (status, body) = try await sendGet(
            transport: udsMarkerInMemoryTransport(), baseURL: inMemoryBaseURL,
            path: "/api/settings/model-profiles",
            headers: [("authorization", "Bearer \(token)")])
        XCTAssertEqual(status, 200, "uds-via-inmemory: authenticated must be 200, got \(status): \(String(decoding: body, as: UTF8.self))")
    }

    func testMatrixHTTPSAuthenticated() async throws {
        let baseURL = try liveHTTPSBaseURL()
        let transport = FicheroClient.liveTransport(transportMode: .https)
        let token = try liveBootstrapToken()
        let (status, _) = try await sendGet(
            transport: transport, baseURL: baseURL,
            path: "/api/settings/model-profiles",
            headers: [("authorization", "Bearer \(token)")])
        XCTAssertEqual(status, 200, "https live: authenticated must be 200 (got \(status))")
    }

    func testMatrixUDSAuthenticated() async throws {
        let socket = try liveUDSPath()
        let baseURL = FicheroClient.makeServerURL(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            transportMode: .uds(path: socket))
        let transport = FicheroClient.liveTransport(transportMode: .uds(path: socket))
        let token = try liveBootstrapToken()
        let (status, _) = try await sendGet(
            transport: transport, baseURL: baseURL,
            path: "/api/settings/model-profiles",
            headers: [("authorization", "Bearer \(token)")])
        XCTAssertEqual(status, 200, "uds live: authenticated must be 200 (got \(status))")
    }

    // MARK: - Matrix: streaming (changes/stream — auth + library-scoped SSE)

    func testMatrixInMemoryStreaming() async throws {
        let (token, restore) = try isolatedToken()
        defer { restore() }
        let (status, firstLine) = try await sendGetFirstLine(
            transport: inMemoryTransport(), baseURL: inMemoryBaseURL,
            path: "/api/changes/stream",
            headers: [
                ("authorization", "Bearer \(token)"),
                ("x-fichero-library-path", "/tmp/inmem-matrix-lib")
            ])
        XCTAssertEqual(status, 200, "inmemory: changes/stream must open 200 (got \(status))")
        XCTAssertEqual(firstLine, ": connected",
                       "inmemory: first SSE frame must be ': connected' (got \(firstLine ?? "nil"))")
    }

    func testMatrixUDSMarkerInMemoryStreaming() async throws {
        // UDS-shaped SSE through the in-memory app: the streaming route is
        // reached and the change hub opens the stream under the "uds" marker's
        // loopback-owner trust — all in-process, no socket.
        let (token, restore) = try isolatedToken()
        defer { restore() }
        let (status, firstLine) = try await sendGetFirstLine(
            transport: udsMarkerInMemoryTransport(), baseURL: inMemoryBaseURL,
            path: "/api/changes/stream",
            headers: [
                ("authorization", "Bearer \(token)"),
                ("x-fichero-library-path", "/tmp/inmem-matrix-lib")
            ])
        XCTAssertEqual(status, 200, "uds-via-inmemory: changes/stream must open 200 (got \(status))")
        XCTAssertEqual(firstLine, ": connected",
                       "uds-via-inmemory: first SSE frame must be ': connected' (got \(firstLine ?? "nil"))")
    }

    func testMatrixHTTPSStreaming() async throws {
        let baseURL = try liveHTTPSBaseURL()
        let transport = FicheroClient.liveTransport(transportMode: .https)
        let token = try liveBootstrapToken()
        // A REAL registered library: the engine enforces a library-path
        // allowlist, so the old hard-coded `/tmp/live-matrix-lib` always 403'd
        // and this live case could never pass against a running engine.
        let library = try await liveLibraryPath(
            transport: transport, baseURL: baseURL, token: token)
        let (status, firstLine) = try await sendGetFirstLine(
            transport: transport, baseURL: baseURL,
            path: "/api/changes/stream",
            headers: [
                ("authorization", "Bearer \(token)"),
                ("x-fichero-library-path", library)
            ])
        XCTAssertEqual(status, 200, "https live: changes/stream must open 200 (got \(status))")
        XCTAssertEqual(firstLine, ": connected",
                       "https live: first SSE frame must be ': connected' (got \(firstLine ?? "nil"))")
    }

    func testMatrixUDSStreaming() async throws {
        let socket = try liveUDSPath()
        let baseURL = FicheroClient.makeServerURL(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            transportMode: .uds(path: socket))
        let transport = FicheroClient.liveTransport(transportMode: .uds(path: socket))
        let token = try liveBootstrapToken()
        // A REAL registered library — see the note in `testMatrixHTTPSStreaming`.
        let library = try await liveLibraryPath(
            transport: transport, baseURL: baseURL, token: token)
        let (status, firstLine) = try await sendGetFirstLine(
            transport: transport, baseURL: baseURL,
            path: "/api/changes/stream",
            headers: [
                ("authorization", "Bearer \(token)"),
                ("x-fichero-library-path", library)
            ])
        XCTAssertEqual(status, 200, "uds live: changes/stream must open 200 (got \(status))")
        XCTAssertEqual(firstLine, ": connected",
                       "uds live: first SSE frame must be ': connected' (got \(firstLine ?? "nil"))")
    }

    // MARK: - Matrix: pool segmentation under N open streams (#4349)

    /// The live-socket acceptance case for #4349: FOUR concurrent SSE
    /// subscriptions (four open libraries' worth) held open while ordinary
    /// request traffic runs. Request traffic must still succeed and the
    /// near-ceiling tripwire must stay silent on BOTH pools.
    ///
    /// Before the fix this failed with AsyncHTTPClient's inherited per-host soft
    /// limit of 8: streams and requests shared one pool, so the fifth-or-so
    /// long-lived stream pinned the last connection and `/api/health` queued
    /// until it timed out. Headless coverage of the same invariant (no engine
    /// required) lives in `ConnectionPoolSegmentationTests`.
    func testMatrixUDSStreamPoolDoesNotStarveRequestTraffic() async throws {
        let socket = try liveUDSPath()
        let baseURL = FicheroClient.makeServerURL(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            transportMode: .uds(path: socket))
        let streamTransport = FicheroClient.liveTransport(
            transportMode: .uds(path: socket), usage: .stream)
        let requestTransport = FicheroClient.liveTransport(
            transportMode: .uds(path: socket), usage: .request)
        let token = try liveBootstrapToken()
        // `/api/changes/stream` is library-scoped and the engine enforces the
        // library-path allowlist, so use a REAL registered library rather than a
        // made-up path (a 403 would prove nothing about pools).
        let library = try await liveLibraryPath(
            transport: requestTransport, baseURL: baseURL, token: token)

        LocalTransportPool.requestPressure.reset()
        LocalTransportPool.streamPressure.reset()

        // Hold four SSE subscriptions open for the duration of the request run.
        // `sendGetFirstLine` would RELEASE the connection (it drops the body once
        // it has a line), so these tasks keep iterating the body instead — that
        // is what "an open library" actually looks like to the pool.
        let streamCount = 4
        let streamTasks = (0..<streamCount).map { index in
            Task {
                var request = HTTPRequest(
                    method: .get, scheme: nil, authority: nil, path: "/api/changes/stream")
                request.headerFields[.accept] = "text/event-stream"
                request.headerFields[.authorization] = "Bearer \(token)"
                if let name = HTTPField.Name("x-fichero-library-path") {
                    request.headerFields[name] = library
                }
                let (response, body) = try await streamTransport.send(
                    request, body: nil, baseURL: baseURL,
                    operationID: "matrix.pool.changesStream.\(index)")
                XCTAssertEqual(response.status.code, 200, "stream \(index) must open 200")
                guard let body else { return }
                for try await _ in body { if Task.isCancelled { break } }
            }
        }

        // Wait until the pool actually reports four held connections (up to 10s),
        // so the request run below happens with the streams genuinely open.
        for _ in 0..<1000 where LocalTransportPool.streamPressure.snapshot().inUse < streamCount {
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTAssertEqual(
            LocalTransportPool.streamPressure.snapshot().inUse, streamCount,
            "all \(streamCount) SSE subscriptions must be open before the request run")

        // Request traffic while the streams are open.
        for index in 0..<12 {
            let (status, _) = try await sendGet(
                transport: requestTransport, baseURL: baseURL, path: "/api/health")
            XCTAssertEqual(
                status, 200,
                "request #\(index) must succeed with \(streamCount) streams open — "
                    + "streams and requests must not share a connection pool")
        }

        XCTAssertEqual(
            LocalTransportPool.streamPressure.snapshot().nearCeilingWarnings, 0,
            "\(streamCount) streams must not approach the stream-pool ceiling")
        XCTAssertEqual(
            LocalTransportPool.requestPressure.snapshot().nearCeilingWarnings, 0,
            "ordinary request traffic must not approach the request-pool ceiling")

        for task in streamTasks { task.cancel() }
    }

    // MARK: - Live-transport env helpers (skip when no live engine is configured)

    private func liveHTTPSBaseURL() throws -> URL {
        guard let raw = ProcessInfo.processInfo.environment["FICHERO_TEST_HTTPS_URL"],
              let url = URL(string: raw), url.scheme?.lowercased().hasPrefix("http") == true else {
            throw XCTSkip("Set FICHERO_TEST_HTTPS_URL to a live engine base URL to exercise the HTTPS matrix.")
        }
        return url
    }

    /// A REAL registered library path from the live engine's registry. The
    /// engine enforces a library-path allowlist, so a made-up path yields 403 —
    /// which would tell us nothing about connection pools. Skips when the
    /// registry is empty.
    private func liveLibraryPath(
        transport: any ClientTransport,
        baseURL: URL,
        token: String
    ) async throws -> String {
        let (status, body) = try await sendGet(
            transport: transport, baseURL: baseURL, path: "/api/registry",
            headers: [("authorization", "Bearer \(token)")])
        guard status == 200,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
              let libraries = json["libraries"] as? [[String: Any]],
              let path = libraries.compactMap({ $0["path"] as? String }).first
        else {
            throw XCTSkip("Live engine has no registered library; cannot open a library-scoped stream.")
        }
        return path
    }

    private func liveUDSPath() throws -> String {
        guard let path = ProcessInfo.processInfo.environment["FICHERO_TEST_UDS_PATH"],
              !path.isEmpty else {
            throw XCTSkip("Set FICHERO_TEST_UDS_PATH to a live engine socket path to exercise the UDS matrix.")
        }
        return path
    }

    /// For live-transport auth, read the real `.api-key` the running engine
    /// wrote. Skip if it isn't present (the live engine isn't up).
    private func liveBootstrapToken() throws -> String {
        guard let url = AuthTokenMiddleware.bootstrapTokenFileURL(),
              let token = try? String(contentsOf: url, encoding: .utf8) else {
            throw XCTSkip("No bootstrap .api-key found; is a live engine running?")
        }
        let trimmed = token.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw XCTSkip("Bootstrap .api-key is empty.") }
        return trimmed
    }
}
#endif