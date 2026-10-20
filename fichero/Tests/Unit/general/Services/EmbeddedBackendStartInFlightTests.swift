//
//  EmbeddedBackendStartInFlightTests.swift
//  FicheroTests
//
//  sharing.switching-restarts-the-engine-once (#5909): a start already in flight is waited for, never skipped, and a
//  switch that restarts the engine ends with one running. See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
import Testing

@MainActor
@Suite("Engine start in flight (#5909)")
struct EmbeddedBackendStartInFlightTests {
    @Test("a start in flight is waited for, not skipped; with none, start begins")
    func inFlightIsAwaited() {
        #expect(EmbeddedBackendService.startDisposition(isStarting: true) == .awaitInFlight)
        #expect(EmbeddedBackendService.startDisposition(isStarting: false) == .begin)
    }

    @Test("a switch starts again unless the engine is running after the wait")
    func anotherStartUnlessRunning() {
        #expect(EmbeddedBackendService.needsAnotherStart(status: .running) == false)
        #expect(EmbeddedBackendService.needsAnotherStart(status: .failed) == true)
    }

    @Test("rapid retries still spawn once: the waiters return only when the first start has ended")
    func waitersReturnAfterTheFirstEnds() async {
        let service = EmbeddedBackendService()
        await withTaskGroup(of: Void.self) { group in
            for _ in 0..<4 { group.addTask { @MainActor in try? await service.start() } }
        }
        #expect(service.startAttemptsPassedGuard == 1)
        #expect(service.isStarting == false)
    }
}
