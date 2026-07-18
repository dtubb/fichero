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
import Foundation
import Testing

@Suite("Port-conflict decision (#3111)")
@MainActor
struct PortConflictDecisionTests {

    // MARK: - Decision table

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
