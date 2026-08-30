//
//  LaunchProbePolicyTests.swift
//  FicheroTests
//
//  The iOS launch probe's grace policy (Daniel, 2026-08-29): the paired Mac
//  being unreachable must not hold the launch story for the transport's 60s
//  deadline. Pure decision table, tested without a network or UI — the
//  spawnWaitStep pattern.
//

@testable import Fichero
import Foundation
import Testing

@Suite("iOS launch probe grace policy (Daniel 2026-08-29)")
struct LaunchProbePolicyTests {

    @Test("grace is a few seconds, far below the 60s transport deadline")
    func graceIsShort() {
        #expect(LaunchProbePolicy.firstProbeGrace <= .seconds(5))
        #expect(LaunchProbePolicy.firstProbeGrace >= .seconds(1))
    }

    @Test("a probe still starting at grace expiry flips to the honest still-connecting status")
    func startingFlips() {
        #expect(
            LaunchProbePolicy.actionOnGraceExpiry(phase: .starting)
                == .markStillConnecting
        )
    }

    @Test("a phase the probe already resolved is the truth — the stale race loser must not overwrite it")
    func resolvedPhasesKept() {
        let resolved: [EngineSession.Phase] = [
            .ready,
            .setupNeeded,
            .unreachable(diagnosis: "down"),
            .authRejected(diagnosis: "bad token"),
            .failed(diagnosis: "exited"),
            .portConflict(pid: 42)
        ]
        for phase in resolved {
            #expect(
                LaunchProbePolicy.actionOnGraceExpiry(phase: phase)
                    == .keepResolvedPhase
            )
        }
    }

    @Test("the still-connecting diagnosis names the host and promises the retry")
    func diagnosisNamesHost() {
        let text = LaunchProbePolicy.stillConnectingDiagnosis(host: "daniels-mac.local")
        #expect(text.contains("daniels-mac.local"))
        #expect(text.lowercased().contains("retry"))
    }
}
