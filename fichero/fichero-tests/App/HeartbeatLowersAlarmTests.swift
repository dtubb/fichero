//
//  HeartbeatLowersAlarmTests.swift
//  FicheroTests
//
//  #4296 — the status island wore a connection error while the backend was
//  demonstrably working. The phase machine could RAISE the alarm (markFailed /
//  markUnreachable / markAuthRejected) but a transient start failure parked
//  the session in a failure phase with NO heartbeat running — so nothing ever
//  lowered it; recovery required a manual Retry. These tests pin (1) the
//  fail → succeed → ready transition, and (2) that every lifecycle failure
//  handler leaves the recovery poller (the heartbeat) running.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
@Suite("Heartbeat lowers the alarm (#4296)")
struct HeartbeatLowersAlarmTests {

    // MARK: - Phase machine: failure phases are recoverable on success

    @Test("failed → heartbeat success → ready, diagnosis cleared")
    func failedThenSuccessIsReady() {
        let session = EngineSession()
        session.markFailed("spawn blew up at launch")
        #expect(!session.isReady)
        #expect(session.diagnosis != nil)

        // The heartbeat's passing probe transition.
        session.markReady()
        #expect(session.phase == .ready)
        #expect(session.diagnosis == nil)
    }

    @Test("unreachable → heartbeat success → ready")
    func unreachableThenSuccessIsReady() {
        let session = EngineSession()
        session.markUnreachable("first heartbeat raced engine startup")
        session.markReady()
        #expect(session.phase == .ready)
        #expect(session.diagnosis == nil)
    }

    @Test("authRejected → heartbeat success → ready")
    func authRejectedThenSuccessIsReady() {
        let session = EngineSession()
        session.markAuthRejected("token race at startup")
        session.markReady()
        #expect(session.phase == .ready)
    }

    // MARK: - Lifecycle: every failure handler leaves the poller running

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    @Test("every connect-failure handler starts the recovery heartbeat")
    func failureHandlersStartHeartbeat() throws {
        let source = try Self.appSource("Services/EngineLifecycleController.swift")

        // The probe-miss branch already re-probed (#3162); the three failure
        // handlers must too, or a transient start failure wears the error
        // badge forever while the app serves data (#4296). 1 probe-miss + 3
        // handlers + 1 finishSuccessfulConnect = 5 call sites.
        let calls = source.components(separatedBy: "appState.startBackendHeartbeat()").count - 1
        #expect(
            calls >= 5,
            "handlePortConflict, handleConnectFailure, and showBackendError must all start the heartbeat so a passing probe can lower the alarm (#4296)"
        )
    }

    @Test("the heartbeat's ready branch lowers the alarm from any phase")
    func heartbeatReadyBranchLowersAlarm() throws {
        let source = try Self.appSource("App/AppState+Heartbeat.swift")
        // `if !isBackendRunning { engine.markReady() … }` — markReady must be
        // reachable from every non-ready phase (isBackendRunning is
        // phase == .ready), i.e. the success path clears failure phases.
        #expect(source.contains("engine.markReady()"))
    }
}
