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
}
