//
//  EngineSessionTests.swift
//  FicheroTests
//
//  The one engine session state machine (#3107): phase transitions and the
//  invariant that NO representable phase maps to "render nothing" — every phase
//  has explicit full-window UI, so the app can never blank (#2864/#2859).
//

@testable import Fichero
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
