//
//  EngineReadinessProbeTests.swift
//  FicheroTests
//
//  The one readiness probe (#3106): classification of health/identity/auth
//  observations into the readiness contract, and the /api/health + /api/registry
//  URL regression (the old checkHealth() hit /health with no /api prefix → 404).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@Suite("EngineReadinessProbe (#3106)")
struct EngineReadinessProbeTests {

    private func classify(
        _ health: Int?,
        nonce: String? = nil,
        expected: String? = nil,
        pid: Int? = nil,
        registry: Int? = nil
    ) -> EngineReadiness {
        EngineReadinessProbe.classify(
            healthStatus: health,
            healthNonce: nonce,
            expectedNonce: expected,
            enginePid: pid,
            registryStatus: registry
        )
    }

    @Test("health 200 + registry 200 → ready")
    func ready() {
        #expect(classify(200, nonce: "n", expected: "n", pid: 1, registry: 200) == .ready)
    }

    @Test("proven-readiness fast path fires only for .ready (#3975)")
    @MainActor
    func provenReadinessFastPathOnlyForReady() {
        // AppState.checkBackendHealthUntilReady short-circuits the redundant
        // re-probe (~3-4 round-trips) ONLY when the spawn already proved `.ready`.
        // Every other value — including nil (remote host / a retry before start) —
        // must fall through to the full probe + #3162 backoff.
        #expect(AppState.shouldReuseProvenReadiness(.ready))
        #expect(AppState.shouldReuseProvenReadiness(nil) == false)
        #expect(AppState.shouldReuseProvenReadiness(.authRejected) == false)
        #expect(AppState.shouldReuseProvenReadiness(.notResponding) == false)
        #expect(AppState.shouldReuseProvenReadiness(.identityMismatch(pid: 123)) == false)
    }

    @Test("registry 401 / 403 → authRejected (the blank-window-401 cause)")
    func authRejected() {
        #expect(classify(200, registry: 401) == .authRejected)
        #expect(classify(200, registry: 403) == .authRejected)
    }

    @Test("auth-failure classifier keeps the stale bootstrap token body")
    func authFailureKeepsStructuredBody() {
        let body = Data(#"{"detail":"local bootstrap token is stale","code":"stale_bootstrap_token"}"#.utf8)
        #expect(EngineReadinessProbe.classifyAuthFailure(statusCode: 401, body: body) == .staleBootstrapToken)
    }

    @Test("registry 404 / other / no response → notResponding (fail-closed)")
    func registryOther() {
        #expect(classify(200, registry: 404) == .notResponding)
        #expect(classify(200, registry: 500) == .notResponding)
        #expect(classify(200, registry: nil) == .notResponding)
    }

    @Test("health not 200 (down / timeout) → notResponding, before any auth")
    func healthDown() {
        #expect(classify(nil, registry: 200) == .notResponding)     // transport error / timeout
        #expect(classify(503, registry: 200) == .notResponding)
    }

    @Test("nonce mismatch → identityMismatch(pid), even if the token would be accepted")
    func nonceMismatch() {
        #expect(classify(200, nonce: "other", expected: "mine", pid: 4242, registry: 200) == .identityMismatch(pid: 4242))
    }

    @Test("adopted engine (no expected nonce) skips identity → ready on registry 200")
    func adoptedSkipsIdentity() {
        #expect(classify(200, nonce: "whatever", expected: nil, pid: 7, registry: 200) == .ready)
    }

}

/// Stubs `GET /api/health` and `GET /api/registry` so the probe's fetch path can
/// be exercised end-to-end through the real generated `FicheroClient` (over an
/// HTTPS mock session — the transport the probe now rides instead of a raw
/// URLSession). The same code path is what a `.uds` client would take; only the
/// concrete transport differs, so HTTPS coverage validates the client-routed
/// fetch + typed-response → status-code mapping.
private final class ReadinessMockURLProtocol: URLProtocol {
    struct Stub { let status: Int; let json: String }
    /// Default health: 200 with a matching nonce + pid, so an unset test is a
    /// deterministic ready-shaped health.
    nonisolated(unsafe) static var health = Stub(status: 200, json: #"{"status":"ok","launch_nonce":"n","engine_pid":123}"#)
    /// Default registry: 200 with the required `LibraryRegistryResponse` shape.
    nonisolated(unsafe) static var registry = Stub(status: 200, json: #"{"libraries":[],"count":0}"#)

    static func reset() {
        health = Stub(status: 200, json: #"{"status":"ok","launch_nonce":"n","engine_pid":123}"#)
        registry = Stub(status: 200, json: #"{"libraries":[],"count":0}"#)
    }

    override static func canInit(with request: URLRequest) -> Bool {
        guard let path = request.url?.path else { return false }
        return path.hasPrefix("/api/health") || path.hasPrefix("/api/registry")
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let stub = request.url?.path.hasPrefix("/api/health") == true ? Self.health : Self.registry
        let response = HTTPURLResponse(
            url: request.url!, statusCode: stub.status, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(stub.json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

/// End-to-end fetch path: the probe fetching health + registry THROUGH the
/// generated `FicheroClient` (not a raw URLSession bound to `hostURL`). Serialized
/// because the mock protocol carries per-test stubs in static state.
@Suite("EngineReadinessProbe fetches through the client", .serialized)
struct EngineReadinessProbeFetchTests {

    @MainActor
    private func makeProbe(expectedNonce: String? = nil) -> EngineReadinessProbe {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ReadinessMockURLProtocol.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://readiness.test")!,
            session: URLSession(configuration: configuration)
        )
        return EngineReadinessProbe(client: client, expectedNonce: expectedNonce)
    }

    @Test("health 200 + matching nonce + registry 200 → ready")
    @MainActor
    func readyThroughClient() async {
        ReadinessMockURLProtocol.reset()
        defer { ReadinessMockURLProtocol.reset() }
        #expect(await makeProbe(expectedNonce: "n").probe() == .ready)
    }

    @Test("registry 401 → authRejected (the token the client attaches was refused)")
    @MainActor
    func authRejectedThroughClient() async {
        ReadinessMockURLProtocol.reset()
        defer { ReadinessMockURLProtocol.reset() }
        ReadinessMockURLProtocol.registry = .init(status: 401, json: #"{"detail":"unauthorized"}"#)
        #expect(await makeProbe(expectedNonce: "n").probe() == .authRejected)
    }

    @Test("health non-200 → notResponding, before any auth (fail-closed)")
    @MainActor
    func healthDownThroughClient() async {
        ReadinessMockURLProtocol.reset()
        defer { ReadinessMockURLProtocol.reset() }
        ReadinessMockURLProtocol.health = .init(status: 503, json: #"{"status":"down"}"#)
        #expect(await makeProbe(expectedNonce: "n").probe() == .notResponding)
    }

    @Test("nonce mismatch → identityMismatch(pid) from the health body")
    @MainActor
    func nonceMismatchThroughClient() async {
        ReadinessMockURLProtocol.reset()
        defer { ReadinessMockURLProtocol.reset() }
        ReadinessMockURLProtocol.health = .init(status: 200, json: #"{"status":"ok","launch_nonce":"other","engine_pid":4242}"#)
        #expect(await makeProbe(expectedNonce: "mine").probe() == .identityMismatch(pid: 4242))
    }

    @Test("authFailure() collects the undocumented 401 body → stale bootstrap token")
    @MainActor
    func authFailureCollectsBodyThroughClient() async {
        ReadinessMockURLProtocol.reset()
        defer { ReadinessMockURLProtocol.reset() }
        ReadinessMockURLProtocol.registry = .init(
            status: 401,
            json: #"{"detail":"local bootstrap token is stale","code":"stale_bootstrap_token"}"#
        )
        #expect(await makeProbe().authFailure() == .staleBootstrapToken)
    }
}

/// #3948: the probe's auth header is derived by `engineAuthHeaders`, which used
/// to block the main actor up to 3s per call (`waitForTokenBlocking`'s
/// Thread.sleep loop) whenever the token was absent — a freeze every heartbeat.
/// It now reads the token once, non-blocking; when there is no token the request
/// is sent header-free and the resulting 401 classifies as `authRejected`, which
/// is the honest outcome (blocking never changed that outcome — it only delayed
/// reaching it). `waitForTokenBlocking` was deleted, so this whole class of
/// main-actor freeze is compiler-unreachable.
@Suite("engineAuthHeaders is non-blocking (#3948)")
struct EngineAuthHeadersTests {

    @Test("an unpaired remote host with no token yields a header-free request")
    func unpairedRemoteHasNoAuthHeader() {
        // A never-paired remote resolves to the .remote token kind, whose Keychain
        // lookup returns nil — so no Authorization header, returned immediately
        // rather than after a 3s blocking wait for a token that will never arrive.
        let headers = engineAuthHeaders(
            for: URL(string: "https://unpaired-host.invalid:9999/api/registry")
        )
        #expect(headers["Authorization"] == nil)
    }

    @Test("an unauthenticated path never carries an Authorization header")
    func unauthenticatedPathSkipsAuth() {
        let headers = engineAuthHeaders(for: URL(string: "https://127.0.0.1:8765/api/health"))
        #expect(headers["Authorization"] == nil)
    }

    @Test("a library-scoped raw request still carries the library header")
    func libraryHeaderIsAttached() {
        let headers = engineAuthHeaders(
            for: URL(string: "https://127.0.0.1:8765/api/documents"),
            libraryPath: "/tmp/Test.fichero"
        )
        #expect(headers["X-Fichero-Library-Path"] == "/tmp/Test.fichero")
    }
}
