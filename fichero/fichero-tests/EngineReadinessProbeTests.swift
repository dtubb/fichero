//
//  EngineReadinessProbeTests.swift
//  FicheroTests
//
//  The one readiness probe (#3106): classification of health/identity/auth
//  observations into the readiness contract, and the /api/health + /api/registry
//  URL regression (the old checkHealth() hit /health with no /api prefix → 404).
//

@testable import Fichero
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

    @Test("probe URLs are /api/health and /api/registry — the /health path-bug regression")
    func probeURLs() {
        let probe = EngineReadinessProbe(hostURL: URL(string: "https://127.0.0.1:8765")!)
        #expect(probe.healthURL.path == "/api/health")
        #expect(probe.registryURL.path == "/api/registry")
    }
}
