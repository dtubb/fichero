//
//  ProbeTransitionLogTests.swift
//  FicheroTests
//
//  A transition log must log TRANSITIONS.
//
//  The readiness probe polls every 500ms in steady state. The first fix for the
//  resulting flood demoted the unchanged line to `.debug`, on the assumption
//  that `.debug` is invisible. It is not: `.debug` is not PERSISTED, but it is
//  fully visible in a live `log stream` — which is where these logs are read.
//  So the demotion produced the worst of both, ~600 identical lines per five
//  minutes while someone is watching and nothing at all afterwards.
//
//  The decision is pure, so the quiet-in-between and the rollup cadence are
//  verified here without a clock, an engine, or a log stream.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
@Suite("Readiness probe steady-state logging")
struct ProbeTransitionLogTests {

    private static let ready = "readiness legs: health=200 registry=200 → ready"
    private static let lost = "readiness legs: health=nil (transport error) → notResponding"
    private static let epoch = Date(timeIntervalSince1970: 1_000_000)

    // MARK: - Transitions always speak

    @Test("the first observation is a transition, with no previous")
    func firstObservationIsATransition() {
        #expect(
            ProbeTransitionLog.emission(
                summary: Self.ready,
                lastSummary: nil,
                steadySince: nil,
                lastSpokeAt: nil,
                now: Self.epoch
            ) == .transition(previous: nil)
        )
    }

    @Test("a changed reading speaks immediately, however recently we spoke")
    func aChangedReadingSpeaksImmediately() {
        // One millisecond after a transition — nowhere near the rollup interval.
        #expect(
            ProbeTransitionLog.emission(
                summary: Self.lost,
                lastSummary: Self.ready,
                steadySince: Self.epoch,
                lastSpokeAt: Self.epoch,
                now: Self.epoch.addingTimeInterval(0.001)
            ) == .transition(previous: Self.ready)
        )
    }

    /// Losing the engine is the one line nobody may miss. It must never be
    /// throttled by how recently something else was said.
    @Test("ready → lost is never throttled")
    func readyToLostIsNeverThrottled() {
        for elapsed in [0.0, 0.5, 1.0, 299.0] {
            #expect(
                ProbeTransitionLog.emission(
                    summary: Self.lost,
                    lastSummary: Self.ready,
                    steadySince: Self.epoch,
                    lastSpokeAt: Self.epoch,
                    now: Self.epoch.addingTimeInterval(elapsed)
                ) == .transition(previous: Self.ready)
            )
        }
    }

    // MARK: - Steady state is silent

    /// The regression this file exists for. At a 500ms poll, five minutes of a
    /// healthy engine is ~600 observations; every one of them must be silent.
    @Test("an unchanged reading says nothing until the rollup is due")
    func steadyStateIsSilent() {
        var spoken = 0
        var time = Self.epoch
        // 600 polls at 500ms = 300s, i.e. right up to the interval.
        for _ in 0..<599 {
            time = time.addingTimeInterval(0.5)
            let emission = ProbeTransitionLog.emission(
                summary: Self.ready,
                lastSummary: Self.ready,
                steadySince: Self.epoch,
                lastSpokeAt: Self.epoch,
                now: time
            )
            if emission != .silent { spoken += 1 }
        }
        #expect(spoken == 0, "a healthy engine must not narrate itself 600 times")
    }

    @Test("the rollup fires once the interval is up, and reports how long it held")
    func rollupFiresAtTheInterval() {
        let due = Self.epoch.addingTimeInterval(ProbeTransitionLog.steadyRollupInterval)
        #expect(
            ProbeTransitionLog.emission(
                summary: Self.ready,
                lastSummary: Self.ready,
                steadySince: Self.epoch,
                lastSpokeAt: Self.epoch,
                now: due
            ) == .rollup(held: ProbeTransitionLog.steadyRollupInterval)
        )
    }

    /// The rollup reports age since the state BEGAN, not since we last spoke —
    /// otherwise every rollup says "unchanged for 5m" no matter how long the
    /// engine has actually been up, which is a number that cannot be wrong and
    /// therefore cannot be informative.
    @Test("the rollup ages from when the state began, not from the last rollup")
    func rollupAgesFromTheStart() {
        let began = Self.epoch
        let spokeAt = began.addingTimeInterval(600)   // two rollups already gone by
        let now = spokeAt.addingTimeInterval(ProbeTransitionLog.steadyRollupInterval)

        #expect(
            ProbeTransitionLog.emission(
                summary: Self.ready,
                lastSummary: Self.ready,
                steadySince: began,
                lastSpokeAt: spokeAt,
                now: now
            ) == .rollup(held: 900)
        )
    }

    @Test("a rollup is followed by silence again")
    func rollupIsFollowedBySilence() {
        let spokeAt = Self.epoch.addingTimeInterval(ProbeTransitionLog.steadyRollupInterval)
        #expect(
            ProbeTransitionLog.emission(
                summary: Self.ready,
                lastSummary: Self.ready,
                steadySince: Self.epoch,
                lastSpokeAt: spokeAt,
                now: spokeAt.addingTimeInterval(1)
            ) == .silent
        )
    }

    // MARK: - The rollup is readable

    @Test("the held duration reads as a duration, not as machine output")
    func heldDurationIsHumanReadable() {
        #expect(ProbeTransitionLog.describe(0) == "0s")
        #expect(ProbeTransitionLog.describe(45) == "45s")
        // 59.6 rounds to 60, which is a minute — the boundary belongs to "1m".
        #expect(ProbeTransitionLog.describe(59.4) == "59s")
        #expect(ProbeTransitionLog.describe(59.6) == "1m")
        #expect(ProbeTransitionLog.describe(300) == "5m")
        #expect(ProbeTransitionLog.describe(300.0000012) == "5m")
        #expect(ProbeTransitionLog.describe(3_600) == "60m")
    }

    /// The interval has to be long enough to be quiet and short enough that a
    /// live watcher sees the engine is still there.
    @Test("the rollup interval is minutes, not seconds")
    func rollupIntervalIsMinutes() {
        #expect(ProbeTransitionLog.steadyRollupInterval >= 60)
        #expect(ProbeTransitionLog.steadyRollupInterval <= 900)
    }
}
