//
//  SpawnedEngineLivenessWaitTests.swift
//  FicheroTests
//
//  #3930 — the engine we spawn is waited on by LIVENESS, not by a clock.
//
//  A fixed budget makes the app race its own subprocess, and whoever wins decides
//  whether the user sees the app or a failure gate. The engine's cold start is
//  import + lifespan + bind (~23s measured), which the app cannot predict and the
//  user cannot influence — so on the one path where the app spawned the child and
//  can therefore KNOW whether it is alive, it waits instead of guessing.
//
//  The decision step is pure, so every timing invariant here is verified without
//  an engine, a process, or a clock.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
@Suite("Spawned engine liveness wait (#3930)")
struct SpawnedEngineLivenessWaitTests {

    // MARK: - A live child is startup, not failure

    /// The regression this exists for: the old budget expired at ~20s while a real
    /// cold engine needs ~23s, so the app gave up ~3s early, showed a gate, and the
    /// user's "Restart Engine" click only appeared to help because the second start
    /// was warm. A live child that has not bound yet must simply keep waiting.
    @Test(
        "a live engine keeps waiting past the old ~20s budget",
        arguments: [20.1, 23.1, 30.0, 60.0, 120.0, 299.0]
    )
    func liveEngineKeepsWaitingPastTheOldBudget(elapsed: TimeInterval) {
        #expect(
            EmbeddedBackendService.spawnWaitStep(
                readiness: .notResponding,
                exitDiagnosis: nil,
                elapsed: elapsed
            ) == .keepWaiting
        )
    }

    /// No non-ready READING ends the wait on its own — only serving or dying does.
    /// In particular `.authRejected` keeps waiting exactly as it did before: this
    /// slice does not reclassify auth failures as "still starting", and
    /// `EngineReadinessProbe.classify` is untouched.
    @Test("no non-ready reading ends the wait by itself")
    func nonReadyReadingsKeepWaiting() {
        let readings: [EngineReadiness] = [.notResponding, .authRejected, .identityMismatch(pid: 42)]
        for reading in readings {
            #expect(
                EmbeddedBackendService.spawnWaitStep(
                    readiness: reading,
                    exitDiagnosis: nil,
                    elapsed: 30
                ) == .keepWaiting,
                "\(reading) is a reading, not a verdict — the child is still alive"
            )
        }
    }

    /// The cap is an insanity bound for a hung process, not a startup budget: the
    /// measured cold start must sit nowhere near it.
    @Test("the insanity cap is not a startup budget")
    func capIsNotAStartupBudget() {
        #expect(EmbeddedBackendService.spawnedEngineInsanityCap >= 240)
        // import 9.6s + lifespan 13.5s + bind 0.5s = 23.1s, measured.
        #expect(EmbeddedBackendService.spawnedEngineInsanityCap > 23.1 * 4)
    }

    // MARK: - A dead child fails immediately, with the reason

    /// Previously a child that died at 2s was polled until the budget expired and
    /// then reported as a generic timeout — the worst of both: slow AND uninformative.
    /// It must fail at once, carrying the terminationHandler's engine.log tail.
    @Test("a dead engine fails immediately and carries the log tail")
    func deadEngineFailsImmediatelyWithLogTail() {
        let diagnosis = """
        The engine exited unexpectedly (code 1).

        ModuleNotFoundError: No module named 'duckdb'
        """
        let step = EmbeddedBackendService.spawnWaitStep(
            readiness: .notResponding,
            exitDiagnosis: diagnosis,
            elapsed: 2  // two seconds in — nowhere near the cap
        )
        #expect(step == .engineExited(diagnosis: diagnosis))
    }

    /// Death outranks the cap, so a child that dies at the boundary still reports
    /// WHY it died rather than the useless "never became ready".
    @Test("an exit diagnosis beats the insanity cap")
    func exitDiagnosisBeatsTheCap() {
        let step = EmbeddedBackendService.spawnWaitStep(
            readiness: .notResponding,
            exitDiagnosis: "The engine exited unexpectedly (code 9).",
            elapsed: 9_999
        )
        #expect(step == .engineExited(diagnosis: "The engine exited unexpectedly (code 9)."))
    }

    // MARK: - The two ends of the wait

    @Test("serving ends the wait, whenever it happens")
    func readyEndsTheWait() {
        #expect(
            EmbeddedBackendService.spawnWaitStep(
                readiness: .ready, exitDiagnosis: nil, elapsed: 0
            ) == .ready
        )
        // Ready outranks the cap: an engine that served must never be failed for
        // having been slow.
        #expect(
            EmbeddedBackendService.spawnWaitStep(
                readiness: .ready, exitDiagnosis: nil, elapsed: 9_999
            ) == .ready
        )
    }

    @Test("an alive-but-never-serving engine trips the cap")
    func hungEngineTripsTheCap() {
        #expect(
            EmbeddedBackendService.spawnWaitStep(
                readiness: .notResponding,
                exitDiagnosis: nil,
                elapsed: EmbeddedBackendService.spawnedEngineInsanityCap
            ) == .neverBecameReady
        )
    }

    // MARK: - Only the spawned path may wait on liveness

    /// Remote hosts, a dev-run uvicorn, and an engine adopted on :8765 are all
    /// processes the app did NOT spawn and cannot watch, so a clock is the only
    /// honest bound for them — and for the dev-external case a timeout is the
    /// right answer anyway: it is the one case where the user has power the app
    /// lacks. Liveness must therefore appear exactly once.
    @Test("liveness waiting is used by exactly one path — the engine we spawn")
    func livenessIsSpawnedPathOnly() throws {
        // #4024: the liveness/wait code (waitForSpawnedBackend / waitForBackend) moved to the
        // +Lifecycle split file; read it so the single-liveness-path assertions still match.
        let source = try Self.appSource("Services/EmbeddedBackendService+Lifecycle.swift")

        let livenessCalls = source.components(separatedBy: "try await waitForSpawnedBackend()").count - 1
        #expect(livenessCalls == 1, "only .spawnOurs may wait on liveness — every other path has no child to watch")

        // The clock-bounded wait still serves remote / dev-external / adopted.
        #expect(source.contains("try await waitForBackend(timeout: 5)"), "remote + dev-external keep their timeout")
        #expect(source.contains("try await waitForBackend(timeout: 30)"), "an adopted engine is not our child")
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
