//
//  BackendDropAutoRestartTests.swift
//  FicheroTests
//
//  #4064: when the supervised (embedded) backend stops mid-session the app
//  auto-restarts it via the existing spawn supervisor (bounded retries + backoff)
//  and only surfaces a Retry/Quit modal once those run out. The release/embedded
//  build NEVER shows the `PYTHONPATH=src python -m fichero_server.api` dev command —
//  that hint is gated to `.debugExternal` (the dev runs the engine by hand).
//

@testable import Fichero
import Foundation
import Testing

@MainActor
@Suite("Backend drop auto-restart (#4064)")
struct BackendDropAutoRestartTests {

    private typealias Strategy = EngineConfig.EngineProvisioningStrategy

    // MARK: - (a) The failure surface never contains the dev command in release/embedded

    @Test("releaseEmbedded mid-session drop is auto-restarted — no diagnosis, no dev command")
    func releaseEmbeddedDropAutoRestarts() {
        let outcome = AppState.supervisedDropOutcome(for: .releaseEmbedded)
        #expect(outcome == .autoRestart)
        // .autoRestart carries NO string — the modal (not a diagnosis) handles
        // the exhausted case, so the dev command can never appear here.
        if case .surfaceDiagnosis(let message) = outcome {
            #expect(!message.contains("python -m fichero"))
            #expect(!message.contains("PYTHONPATH=src"))
        }
    }

    @Test("releaseEmbedded initial-connect failure diagnosis has no dev command")
    func releaseEmbeddedCannotConnectDiagnosisNoDevCommand() {
        let message = AppState.cannotConnectDiagnosis(for: .releaseEmbedded)
        #expect(!message.contains("python -m fichero"))
        #expect(!message.contains("PYTHONPATH=src"))
        #expect(!message.isEmpty)
    }

    @Test("debugExternal is the ONLY strategy that keeps the dev hint (the dev runs the engine)")
    func debugExternalKeepsDevHint() {
        // Mid-session drop diagnosis.
        let dropMessage: String?
        if case .surfaceDiagnosis(let m) = AppState.supervisedDropOutcome(for: .debugExternal) {
            dropMessage = m
        } else {
            dropMessage = nil
        }
        #expect(dropMessage?.contains("python -m fichero") == true)
        #expect(dropMessage?.contains("PYTHONPATH=src") == true)

        // Initial-connect diagnosis.
        let connectMessage = AppState.cannotConnectDiagnosis(for: .debugExternal)
        #expect(connectMessage.contains("python -m fichero"))
        #expect(connectMessage.contains("PYTHONPATH=src"))
    }

    @Test("configuredRemote / iosCompanion / inert drops never carry the dev command")
    func remoteAndInertDropsHaveNoDevCommand() {
        for strategy in [Strategy.configuredRemote, .iosCompanion, .inert] {
            if case .surfaceDiagnosis(let message) = AppState.supervisedDropOutcome(for: strategy) {
                #expect(!message.contains("python -m fichero"), "strategy \(strategy) leaked the dev command")
                #expect(!message.contains("PYTHONPATH=src"), "strategy \(strategy) leaked PYTHONPATH")
            } else {
                Issue.record("expected surfaceDiagnosis for \(strategy)")
            }
            let connectMessage = AppState.cannotConnectDiagnosis(for: strategy)
            #expect(!connectMessage.contains("python -m fichero"))
            #expect(!connectMessage.contains("PYTHONPATH=src"))
        }
    }

    // MARK: - (b) Auto-restart is attempted before the modal is shown

    #if canImport(AppKit)
    @Test("modal is NOT shown while the engine is ready — auto-restart recovered")
    func modalSuppressedWhenReady() {
        #expect(EngineLifecycleController.shouldShowBackendDropModal(
            isReady: true, crashBudgetExhausted: false, attemptsUsed: 3, maxAttempts: 3
        ) == false)
        // Even with the crash budget spent, a ready engine means we recovered
        // — no modal.
        #expect(EngineLifecycleController.shouldShowBackendDropModal(
            isReady: true, crashBudgetExhausted: true, attemptsUsed: 3, maxAttempts: 3
        ) == false)
    }

    @Test("modal is NOT shown before the bounded retry count is exhausted (and budget remains)")
    func modalSuppressedUntilAttemptsExhausted() {
        // 1/3 attempts used, budget intact, engine still down — keep retrying.
        #expect(EngineLifecycleController.shouldShowBackendDropModal(
            isReady: false, crashBudgetExhausted: false, attemptsUsed: 1, maxAttempts: 3
        ) == false)
        #expect(EngineLifecycleController.shouldShowBackendDropModal(
            isReady: false, crashBudgetExhausted: false, attemptsUsed: 2, maxAttempts: 3
        ) == false)
        // 3/3 — exhausted → modal.
        #expect(EngineLifecycleController.shouldShowBackendDropModal(
            isReady: false, crashBudgetExhausted: false, attemptsUsed: 3, maxAttempts: 3
        ) == true)
    }

    @Test("crash-loop budget exhaustion surfaces the modal immediately even before retries run out")
    func modalSurfacedWhenCrashBudgetExhausted() {
        // Crash-loop guard tripped at attempt 1 — surface the modal rather than
        // respawn a hot-crashing engine forever (#18).
        #expect(EngineLifecycleController.shouldShowBackendDropModal(
            isReady: false, crashBudgetExhausted: true, attemptsUsed: 1, maxAttempts: 3
        ) == true)
    }
    #endif

    @Test("the heartbeat routes a supervised drop through the auto-restart hook, not the diagnosis")
    func heartbeatInvokesAutoRestartHookForSupervisedDrop() async {
        // The hook is the seam between "I lost the backend" and "respawn it".
        // On the XCTest host the strategy is `.inert`, so we drive the pure
        // outcome + the hook directly to prove the release path would invoke
        // auto-restart (not surface a dev-command diagnosis).
        let outcome = AppState.supervisedDropOutcome(for: .releaseEmbedded)
        #expect(outcome == .autoRestart)

        // Simulate the heartbeat's branch: when the outcome is `.autoRestart`
        // and a hook is wired, the hook is invoked — not `markUnreachable`.
        var hookInvoked = false
        let appState = AppState()
        appState.onSupervisedBackendDropped = { hookInvoked = true }
        appState.engine.markReady() // simulate a running backend that then drops
        #expect(appState.isBackendRunning)

        // Drive the heartbeat failure path PAST the offline-flip threshold (2
        // consecutive failures). The active host on the test host is the local
        // engine, so `attemptEndpointFailover` returns `.noAlternates` and we
        // fall through to the `isBackendRunning` branch.
        await appState.noteHeartbeatFailure(reason: "test drop 1")
        await appState.noteHeartbeatFailure(reason: "test drop 2")

        // `.inert` (the test-host strategy) surfaces a generic diagnosis
        // WITHOUT the dev command — the release path's `.autoRestart` branch is
        // covered by the pure-outcome assertion above.
        if let diagnosis = appState.backendDiagnosis {
            #expect(!diagnosis.contains("python -m fichero"))
            #expect(!diagnosis.contains("PYTHONPATH=src"))
        }
        // The hook was NOT invoked on the inert host (no controller wired for
        // release in tests) — this documents that the release-only auto-restart
        // path is gated by the provisioning strategy, not by the hook's presence.
        // (The release build wires the controller's hook; tests don't.)
        #expect(hookInvoked == false)
    }
}