//
//  PortConflictDecisionTests.swift
//  FicheroTests
//
//  Port-conflict decision moves in-window (#3111): a process we didn't spawn
//  holding :8765 is a `portConflict(pid)` session phase rendered in the window,
//  NOT a pre-window NSAlert that could self-terminate. The pure decision below
//  is separated from the lsof/kill syscalls so every branch is deterministic.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@Suite("Port-conflict decision (#3111)")
@MainActor
struct PortConflictDecisionTests {

    private typealias Ownership = EmbeddedBackendService.EngineOwnership

    // MARK: - Engine ownership table

    @Test("release embedded spawn is owned and stopped on quit")
    func releaseEmbeddedSpawnIsOwned() {
        #expect(
            EmbeddedBackendService.engineOwnership(
                strategy: .releaseEmbedded,
                transportMode: .uds(path: "/tmp/fichero.sock"),
                portResolution: .spawnOurs
            ) == .ownedEmbedded
        )
        #expect(!Ownership.ownedEmbedded.isExternalBackend)
    }

    @Test("release embedded user-approved adoption is external and left running")
    func releaseEmbeddedAdoptionIsExternal() {
        #expect(
            EmbeddedBackendService.engineOwnership(
                strategy: .releaseEmbedded,
                transportMode: .https,
                portResolution: .adoptExisting
            ) == .adoptedExternal
        )
        #expect(Ownership.adoptedExternal.isExternalBackend)
    }

    @Test("dev UDS engine is owned so app quit tears it down")
    func debugUDSEngineIsOwned() {
        #expect(
            EmbeddedBackendService.engineOwnership(
                strategy: .debugExternal,
                transportMode: .uds(path: "/tmp/fichero-dev.sock"),
                portResolution: nil
            ) == .ownedEmbedded
        )
    }

    @Test("adopted Debug HTTPS engine remains external")
    func debugHTTPSEngineIsExternal() {
        #expect(
            EmbeddedBackendService.engineOwnership(
                strategy: .debugExternal,
                transportMode: .https,
                portResolution: nil
            ) == .adoptedExternal
        )
    }

    @Test("configured and inert strategies never own lifecycle")
    func nonSpawningStrategiesAreExternal() {
        #expect(
            EmbeddedBackendService.engineOwnership(strategy: .configuredRemote, transportMode: .https, portResolution: nil)
                == .adoptedExternal
        )
        #expect(
            EmbeddedBackendService.engineOwnership(strategy: .iosCompanion, transportMode: .https, portResolution: nil)
                == .adoptedExternal
        )
        #expect(
            EmbeddedBackendService.engineOwnership(strategy: .inert, transportMode: .https, portResolution: nil)
                == .adoptedExternal
        )
    }

    // MARK: - Port-conflict decision table

    @Test("port free → spawn (no conflict)")
    func freePortSpawns() {
        #expect(EmbeddedBackendService.portConflictAction(holderPID: nil, pendingChoice: nil) == .spawn)
    }

    @Test("foreign holder + no decision → surface the portConflict phase, never adopt or spawn")
    func foreignHolderSurfacesPhase() {
        let action = EmbeddedBackendService.portConflictAction(holderPID: 4242, pendingChoice: nil)
        #expect(action == .surfacePhase(pid: 4242))
        // The invariant: no silent adoption and no silent kill (#2863).
        #expect(action != .adopt)
        #expect(action != .spawn)
    }

    @Test("Stop it → spawn (caller SIGTERMs the holder first)")
    func stopItSpawns() {
        #expect(
            EmbeddedBackendService.portConflictAction(holderPID: 4242, pendingChoice: .stopIt) == .spawn
        )
    }

    @Test("Use it → adopt (still gated on the authenticated probe downstream)")
    func useItAdopts() {
        #expect(
            EmbeddedBackendService.portConflictAction(holderPID: 4242, pendingChoice: .useIt) == .adopt
        )
    }

    // MARK: - Diagnosis string

    @Test("portConflict error names the holding PID and the port")
    func portConflictErrorNamesPidAndPort() {
        let message = BackendError.portConflict(pid: 4242).errorDescription ?? ""
        #expect(message.contains("4242"))
        #expect(message.contains("8765"))
    }

    @Test("portConflict error tolerates an unknown PID")
    func portConflictErrorUnknownPid() {
        let message = BackendError.portConflict(pid: nil).errorDescription ?? ""
        #expect(message.contains("unknown"))
        #expect(message.contains("8765"))
    }

    // MARK: - Session phase renders in-window

    @MainActor
    @Test("portConflict is a non-ready phase with a PID-bearing diagnosis (renders the connection view, not blank)")
    func portConflictPhaseIsRenderable() {
        // The gate renders BackendConnectionView for every non-ready phase, so a
        // portConflict must carry a diagnosis and never map to ready (#3107/#3111).
        let session = EngineSession()
        session.markPortConflict(pid: 4242)
        #expect(!session.isReady)
        #expect(session.diagnosis?.contains("4242") == true)
        if case .portConflict(let pid) = session.phase {
            #expect(pid == 4242)
        } else {
            Issue.record("expected portConflict phase")
        }
    }
}

// MARK: - #4896 orphan-sweep-precedes-spawn-decision

/// spec: engine-startup-lifecycle `engine.orphan-sweep-precedes-spawn-decision`
/// (#4896, tracing f9a737d5f/#4690): `resolvePortConflict` must not return a
/// spawn decision until the orphan-engine sweep has fully completed — the
/// bug ed436c69a introduced was a detached, un-awaited sweep that could land
/// AFTER the app's own fresh engine had already spawned and kill it. These
/// tests drive the REAL `resolvePortConflict`, injecting the sweep and the
/// transport mode so the assertion is on the real function's actual ordering,
/// not a stand-in helper that would still pass if the call site dropped the
/// await (a `sweepBeforeSpawnDecision`-shaped helper was rejected for exactly
/// this reason). `.uds` is chosen so the port pre-flight does not apply
/// (`portPreflightApplies(transportMode:)` is false for it) — no port/pid
/// syscalls run, so the ONLY thing between "sweep starts" and "the function
/// returns" is the sweep itself.
@Suite("Orphan sweep precedes the spawn decision (#4896)")
@MainActor
struct OrphanSweepPrecedesSpawnDecisionTests {

    @Test("a slow sweep has already finished by the time resolvePortConflict returns .spawnOurs")
    func sweepCompletesBeforeSpawnDecisionReturns() async throws {
        let service = EmbeddedBackendService()
        var sweepFinished = false

        let resolution = try await service.resolvePortConflict(
            sweep: {
                try? await Task.sleep(nanoseconds: 50_000_000)  // 50ms — slow on purpose
                sweepFinished = true
            },
            transportMode: .uds(path: "/tmp/fichero-orphan-sweep-test.sock")
        )

        #expect(resolution == .spawnOurs)
        // This proves resolvePortConflict awaits WHATEVER it is handed — it
        // does not, by itself, prove the PRODUCTION default (awaitedOrphanSweep)
        // still awaits `terminate()`. That's pinned directly below by
        // `awaitedOrphanSweepWaitsForTerminate`, against the real default.
        #expect(sweepFinished == true)
    }

    @Test("the sweep runs exactly once per call")
    func sweepInvokedExactlyOnce() async throws {
        let service = EmbeddedBackendService()
        var sweepCallCount = 0

        _ = try await service.resolvePortConflict(
            sweep: { sweepCallCount += 1 },
            transportMode: .uds(path: "/tmp/fichero-orphan-sweep-test.sock")
        )

        #expect(sweepCallCount == 1)
    }
}

/// Thread-safe flag box for a test that sets its result from INSIDE a
/// `Task.detached` closure (which must be `@Sendable`) while the test method
/// itself runs `@MainActor` — a bare `var` there would be a data race.
///
/// Every member is `nonisolated`: this test target defaults to MainActor
/// isolation, and `set()` is called from a detached, off-main task.
private final class LockedFlag: @unchecked Sendable {
    private nonisolated(unsafe) let lock = NSLock()
    private nonisolated(unsafe) var value = false

    nonisolated init() {}

    nonisolated func set() {
        lock.lock()
        value = true
        lock.unlock()
    }

    nonisolated func get() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return value
    }
}

/// spec: engine-startup-lifecycle `engine.orphan-sweep-precedes-spawn-decision`
/// (#4896) — this is the test pinned directly against WHERE f9a737d5f's
/// regression actually lived: the production DEFAULT `terminate:` closure's
/// `.value` inside `awaitedOrphanSweep` itself, not the `resolvePortConflict`
/// call site (which the tests above already cover, and which would still
/// pass even if this default regressed — they inject their own sweep).
/// Drop the `.value` in `awaitedOrphanSweep` and this test fails.
@Suite("awaitedOrphanSweep awaits its detached terminate() (#4896)")
@MainActor
struct AwaitedOrphanSweepTests {

    @Test("does not return until the detached terminate() call has finished")
    func awaitedOrphanSweepWaitsForTerminate() async {
        let flag = LockedFlag()

        await EmbeddedBackendService.awaitedOrphanSweep(terminate: {
            Thread.sleep(forTimeInterval: 0.05)  // blocks the detached task ~50ms
            flag.set()
        })

        #expect(flag.get() == true)
    }
}
