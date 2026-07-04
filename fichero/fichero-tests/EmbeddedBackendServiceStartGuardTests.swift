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
