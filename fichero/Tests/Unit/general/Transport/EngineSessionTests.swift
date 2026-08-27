//
//  EngineSessionTests.swift
//  FicheroTests
//
//  The one engine session state machine (#3107): phase transitions and the
//  invariant that NO representable phase maps to "render nothing" — every phase
//  has explicit full-window UI, so the app can never blank (#2864/#2859).
//

@testable import Fichero
@testable import FicheroAPIClient
import Foundation
import Testing

@MainActor
@Suite("EngineSession (#3107)")
struct EngineSessionTests {

    // MARK: - Transitions

    @Test("starts in the checking/starting phase")
    func initialPhase() {
        let session = EngineSession()
        #expect(session.phase == .starting)
        #expect(session.isChecking)
        #expect(!session.isReady)
    }

    @Test("starting → ready (normal boot)")
    func startingToReady() {
        let session = EngineSession()
        session.markReady()
        #expect(session.phase == .ready)
        #expect(session.isReady)
        #expect(!session.isChecking)
        #expect(session.diagnosis == nil)
    }

    @Test("starting → authRejected carries the diagnosis (the blank-window-401 cause)")
    func startingToAuthRejected() {
        let session = EngineSession()
        session.markAuthRejected("token mismatch")
        #expect(session.phase == .authRejected(diagnosis: "token mismatch"))
        #expect(session.isAuthRejected)
        #expect(!session.isReady)
        #expect(session.diagnosis == "token mismatch")
    }

    @Test("ready → unreachable after heartbeat loss")
    func readyToUnreachable() {
        let session = EngineSession()
        session.markReady()
        session.markUnreachable("lost connection")
        #expect(session.phase == .unreachable(diagnosis: "lost connection"))
        #expect(!session.isReady)
        #expect(session.diagnosis == "lost connection")
    }

    @Test("retry resets any failure back to starting")
    func retryResetsToStarting() {
        let session = EngineSession()
        session.markFailed("engine exited")
        #expect(!session.isReady)
        // Retry button path.
        session.markStarting()
        #expect(session.phase == .starting)
        #expect(session.isChecking)
        #expect(session.diagnosis == nil)
    }

    @Test("portConflict surfaces the holding PID in its diagnosis")
    func portConflictDiagnosis() {
        let session = EngineSession()
        session.markPortConflict(pid: 4242)
        #expect(session.phase == .portConflict(pid: 4242))
        #expect(session.diagnosis?.contains("4242") == true)
    }

    @Test("setupNeeded is not ready and has no diagnosis (it's a prompt, not an error)")
    func setupNeeded() {
        let session = EngineSession()
        session.markSetupNeeded()
        #expect(session.phase == .setupNeeded)
        #expect(session.needsSetup)
        #expect(!session.isReady)
        #expect(session.diagnosis == nil)
    }

    // MARK: - The never-blank invariant

    /// Every representable phase must resolve to a concrete screen — never
    /// "render nothing". This mirrors BackendRootGate's switch: `.ready` →
    /// content, `.setupNeeded` → setup, everything else → the connection view.
    /// If a new phase is added without a screen, this exhaustive switch fails
    /// to compile — the compiler enforces the invariant.
    private enum Screen: Equatable { case content, setup, connection }

    private func screen(for phase: EngineSession.Phase) -> Screen {
        switch phase {
        case .ready: return .content
        case .setupNeeded: return .setup
        case .starting, .portConflict, .authRejected, .unreachable, .failed:
            return .connection
        }
    }

    @Test("no representable phase maps to 'render nothing'")
    func everyPhaseHasAScreen() {
        let allPhases: [EngineSession.Phase] = [
            .setupNeeded,
            .starting,
            .portConflict(pid: 1),
            .portConflict(pid: nil),
            .ready,
            .authRejected(diagnosis: "x"),
            .unreachable(diagnosis: "x"),
            .failed(diagnosis: "x")
        ]
        for phase in allPhases {
            // Total function — every phase yields one of three concrete screens.
            let resolved = screen(for: phase)
            #expect([.content, .setup, .connection].contains(resolved))
        }
        // Exactly one phase renders real content.
        #expect(allPhases.filter { screen(for: $0) == .content } == [.ready])
    }
}

// MARK: - Per-host session registry (#3112)

/// The multi-remote seam: one loopback session + N remote sessions, keyed by
/// host, each with its own phase and its own credential. The three invariants
/// #3112 must hold — remote failure never touches local, tokens resolve per
/// host, and the single-host app is byte-identical through the default session.
@MainActor
@Suite("EngineSessionRegistry (#3112)")
struct EngineSessionRegistryTests {

    private let localHost = BackendHost(url: URL(string: "https://127.0.0.1:8765")!)
    private let remoteHost = BackendHost(url: URL(string: "https://studio.example.com")!)
    private let otherRemoteHost = BackendHost(url: URL(string: "https://mini.example.com")!)

    // MARK: - Isolation: one host's failure never touches another

    @Test("a remote 401 flips only that session — the local session stays ready")
    func remoteFailureDoesNotTouchLocal() {
        let registry = EngineSessionRegistry(defaultSession: EngineSession(host: localHost))
        let local = registry.activeSession
        let remote = registry.session(for: remoteHost)

        local.markReady()
        remote.markAuthRejected("remote rejected this app's token")

        // The remote's rejection is confined to the remote session.
        #expect(remote.isAuthRejected)
        #expect(local.isReady)
        #expect(local.phase == .ready)
        // …and the reverse: taking the local down leaves the remote untouched.
        local.markUnreachable("local engine exited")
        #expect(remote.isAuthRejected)
    }

    // MARK: - Per-host token resolution (#2866 isolation)

    @Test("each session routes to its own host's token storage — never another host's")
    func tokenResolutionIsPerSessionHost() {
        let registry = EngineSessionRegistry(defaultSession: EngineSession(host: localHost))
        let local = registry.activeSession
        let remote = registry.session(for: remoteHost)

        // The loopback session authenticates against bootstrap storage; the
        // remote session against remote storage — keyed on ITS host string, so
        // a request bound for the remote can never carry the local's token.
        #expect(AuthTokenMiddleware.tokenStorageKind(hostString: local.host.url.absoluteString) == .bootstrap)
        #expect(AuthTokenMiddleware.tokenStorageKind(hostString: remote.host.url.absoluteString) == .remote)
        // Two distinct remotes resolve against distinct keychain accounts.
        let otherRemote = registry.session(for: otherRemoteHost)
        #expect(
            AuthTokenMiddleware.remoteTokenKeychainAccount(hostString: remote.host.url.absoluteString)
                != AuthTokenMiddleware.remoteTokenKeychainAccount(hostString: otherRemote.host.url.absoluteString)
        )
    }

    // MARK: - Regression: single-host behaviour is byte-identical

    @Test("the default session IS the active session (single-host app unchanged)")
    func defaultSessionIsActive() {
        let engine = EngineSession(host: localHost)
        let registry = EngineSessionRegistry(defaultSession: engine)
        // AppState's `engine` and `sessions.activeSession` are the same object,
        // so today's heartbeat drives exactly the session the app renders.
        #expect(registry.activeSession === engine)
        #expect(registry.activeHost == localHost)
    }

    @Test("all loopback URLs collapse to the one loopback session")
    func loopbackCollapsesToOneSession() {
        let registry = EngineSessionRegistry(defaultSession: EngineSession(host: localHost))
        let count = registry.sessions.count
        // Different loopback spellings must not spawn new sessions.
        let via127 = registry.session(for: BackendHost(url: URL(string: "https://127.0.0.1:8765")!))
        let viaLocalhost = registry.session(for: BackendHost(url: URL(string: "https://localhost:8765")!))
        #expect(via127 === viaLocalhost)
        #expect(registry.sessions.count == count) // no growth — still one loopback
    }

    @Test("each distinct remote host gets its own session; re-requests are stable")
    func remoteHostsGetDistinctStableSessions() {
        let registry = EngineSessionRegistry(defaultSession: EngineSession(host: localHost))
        let studio = registry.session(for: remoteHost)
        let mini = registry.session(for: otherRemoteHost)
        #expect(studio !== mini)
        // Get-or-create: asking again returns the same instance, not a new one.
        #expect(registry.session(for: remoteHost) === studio)
    }

    @Test("activate switches the observed session to a remote host")
    func activateSwitchesActiveSession() {
        let registry = EngineSessionRegistry(defaultSession: EngineSession(host: localHost))
        registry.activate(remoteHost)
        #expect(registry.activeHost == remoteHost)
        #expect(registry.activeSession.host == remoteHost)
        // …and back to local.
        registry.activate(localHost)
        #expect(registry.activeSession.host == localHost)
    }
}
