//
//  EmbeddedBackendServiceStartGuardTests.swift
//  FicheroTests
//
//  One poller + one retry entry point (#3108): the re-entrancy guard on
//  `start()` is the invariant that keeps N rapid retries from spawning a second
//  engine or racing the first readiness probe. Because `start()` is @MainActor,
//  the guard is deterministic — MainActor's serial executor runs the first
//  call's synchronous guard-check + flag-set uninterrupted before its first
//  `await`, so every concurrent sibling observes the flag and bounces.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
@Suite("EmbeddedBackendService start guard (#3108)")
struct EmbeddedBackendServiceStartGuardTests {

    @Test("N concurrent retries pass the start guard exactly once — one spawn attempt")
    func oneSpawnUnderRapidRetries() async {
        let service = EmbeddedBackendService()
        #expect(service.startAttemptsPassedGuard == 0)
        #expect(service.isStarting == false)

        // Fire eight retries at once. On the XCTest host `start()` takes the
        // safe "connect-to-external-if-up, else no-op" branch (it never spawns a
        // real engine), so this exercises the guard, not process launch.
        await withTaskGroup(of: Void.self) { group in
            for _ in 0..<8 {
                group.addTask { @MainActor in try? await service.start() }
            }
        }

        // Only the first call got past the guard; the other seven bounced.
        #expect(service.startAttemptsPassedGuard == 1)
        // The in-flight flag resets once the call completes (defer).
        #expect(service.isStarting == false)
    }

    @Test("guard is re-entrant across sequential retries, not a one-shot latch")
    func guardResetsBetweenAttempts() async {
        let service = EmbeddedBackendService()

        try? await service.start()
        #expect(service.startAttemptsPassedGuard == 1)
        #expect(service.isStarting == false)

        // A later retry (after the first finished) must pass the guard again —
        // otherwise a genuine reconnect could never re-probe.
        try? await service.start()
        #expect(service.startAttemptsPassedGuard == 2)
        #expect(service.isStarting == false)
    }
}

/// A new window/tab's connect trigger must reuse the app-level connection rather
/// than reprovision the backend (#3394/#3407).
@Suite("Window-lifecycle connection reuse (#3394)")
@MainActor
struct ConnectionReuseDecisionTests {

    @Test("a new window on a running+ready backend attaches — no reconnect")
    func newWindowReusesRunningConnection() {
        #expect(EmbeddedBackendService.shouldReuseExistingConnection(
            restart: false, status: .running, isBackendReady: true) == true)
    }

    @Test("the first/not-yet-connected window proceeds to connect")
    func firstWindowConnects() {
        #expect(EmbeddedBackendService.shouldReuseExistingConnection(
            restart: false, status: .stopped, isBackendReady: false) == false)
    }

    @Test("an explicit Retry always re-runs, even when running")
    func retryAlwaysReconnects() {
        #expect(EmbeddedBackendService.shouldReuseExistingConnection(
            restart: true, status: .running, isBackendReady: true) == false)
    }

    @Test("running but not-yet-ready does not short-circuit the readiness probe")
    func runningButNotReadyStillConnects() {
        #expect(EmbeddedBackendService.shouldReuseExistingConnection(
            restart: false, status: .running, isBackendReady: false) == false)
    }

    @Test("a failed/starting backend never counts as reusable")
    func failedOrStartingNotReused() {
        #expect(EmbeddedBackendService.shouldReuseExistingConnection(
            restart: false, status: .failed, isBackendReady: true) == false)
        #expect(EmbeddedBackendService.shouldReuseExistingConnection(
            restart: false, status: .starting, isBackendReady: true) == false)
    }

    // MARK: - Native tab + split lifecycle (#3407)

    @Test("opening a native TAB reuses the connection — tabs open the same guarded scene")
    func nativeTabReusesConnection() {
        // WindowOpener.open(asTab: true) calls openWindow(id: "main"), the same
        // scene a new window opens, whose `.task` runs connectBackend(restart:
        // false). So a tab hits the identical reuse decision as a new window —
        // no re-auth, no backend restart. `addTabbedWindow` never touches the
        // backend. (#3407, narrowed scope of #3394.)
        #expect(EmbeddedBackendService.shouldReuseExistingConnection(
            restart: false, status: .running, isBackendReady: true) == true)
    }

    @Test("a window SPLIT never reprovisions — it is an in-window view, not a scene")
    func windowSplitDoesNotReprovision() {
        // A SplittablePane triggers no connect at all (no new scene, no
        // openWindow). This documents that the ONLY paths reaching connectBackend
        // are window/tab scene mounts (restart: false → reuse) and explicit Retry
        // (restart: true). There is no restart:false-on-a-connected-backend path
        // that reprovisions, so a split can't either. (#3407)
        #expect(EmbeddedBackendService.shouldReuseExistingConnection(
            restart: false, status: .running, isBackendReady: true) == true)
    }
}

/// The spawned engine's security posture (auth on/off, bind surface) must come
/// only from the FICHERO_* the app sets — never from a stray FICHERO_* inherited
/// from the shell that launched the app (#3933). `childEnvironmentBase` strips
/// every inherited FICHERO_* before the app layers its own on top.
@Suite("Spawned-engine environment sanitisation (#3933)")
@MainActor
struct SpawnedEngineEnvironmentTests {

    @Test("inherited FICHERO_* keys are stripped from the child's base env")
    func inheritedFicheroVarsAreStripped() {
        let inherited = [
            // The two the issue calls out: auth kill-switch + LAN bind widening.
            "FICHERO_DISABLE_AUTH": "1",
            "FICHERO_LAN_HOST": "0.0.0.0",
            "FICHERO_ALLOW_NON_LOOPBACK_BIND": "I_UNDERSTAND_SHARED_SECRET_RISK",
            // A not-yet-invented FICHERO_* must fail closed too.
            "FICHERO_SOME_FUTURE_FLAG": "danger",
            // Non-FICHERO vars the interpreter needs must survive untouched.
            "PATH": "/usr/bin:/bin",
            "HOME": "/Users/test",
            "LANG": "en_US.UTF-8"
        ]

        let base = EmbeddedBackendService.childEnvironmentBase(inheriting: inherited)

        // No FICHERO_* survives inheritance — the app is the only source.
        #expect(base.keys.allSatisfy { !$0.hasPrefix("FICHERO_") })
        #expect(base["FICHERO_DISABLE_AUTH"] == nil)
        #expect(base["FICHERO_LAN_HOST"] == nil)
        #expect(base["FICHERO_ALLOW_NON_LOOPBACK_BIND"] == nil)
        #expect(base["FICHERO_SOME_FUTURE_FLAG"] == nil)

        // Everything else passes through so the bundled interpreter still runs.
        #expect(base["PATH"] == "/usr/bin:/bin")
        #expect(base["HOME"] == "/Users/test")
        #expect(base["LANG"] == "en_US.UTF-8")
    }

    @Test("an env with no FICHERO_* is returned unchanged")
    func nonFicheroEnvIsUntouched() {
        let inherited = ["PATH": "/bin", "TMPDIR": "/tmp", "USER": "test"]
        #expect(EmbeddedBackendService.childEnvironmentBase(inheriting: inherited) == inherited)
    }
}

/// The engine's `terminationHandler` must decode `terminationReason`: for
/// `.uncaughtSignal` the `terminationStatus` is the SIGNAL NUMBER, so a SIGPIPE
/// (13) must read as "signal 13 SIGPIPE", never the false "exit code 13" that
/// the old status-only path reported. For `.exit` it is a real exit code.
@Suite("Engine termination decoding (SIGPIPE vs exit code)")
struct EngineTerminationDecodingTests {

    @Test("SIGPIPE (signal 13) is decoded as a signal, not exit code 13")
    func sigpipeDecodesAsSignal() {
        let described = EmbeddedBackendService.describeTermination(
            status: SIGPIPE, reason: .uncaughtSignal
        )
        #expect(described == "signal 13 SIGPIPE")
        // The regression we are guarding against: it must NOT read as an exit code.
        #expect(!described.contains("exit code"))
    }

    @Test("a real non-zero exit code is decoded as an exit code")
    func nonZeroExitDecodesAsExit() {
        #expect(EmbeddedBackendService.describeTermination(
            status: 1, reason: .exit) == "exit code 1")
        #expect(EmbeddedBackendService.describeTermination(
            status: 13, reason: .exit) == "exit code 13")
    }

    @Test("other known signals decode to their mnemonics")
    func otherSignalsDecode() {
        #expect(EmbeddedBackendService.describeTermination(
            status: SIGKILL, reason: .uncaughtSignal) == "signal 9 SIGKILL")
        #expect(EmbeddedBackendService.describeTermination(
            status: SIGTERM, reason: .uncaughtSignal) == "signal 15 SIGTERM")
        #expect(EmbeddedBackendService.describeTermination(
            status: SIGSEGV, reason: .uncaughtSignal) == "signal 11 SIGSEGV")
    }

    @Test("a clean exit (code 0) is still described as an exit code")
    func cleanExitDecodes() {
        #expect(EmbeddedBackendService.describeTermination(
            status: 0, reason: .exit) == "exit code 0")
    }
}
