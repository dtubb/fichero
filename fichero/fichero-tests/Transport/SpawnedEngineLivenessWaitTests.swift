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

    /// Silence is the only reading that means "still starting". A 401 and a
    /// foreign nonce are the engine ANSWERING, and each has its own remedy.
    @Test("only silence is still-starting")
    func onlySilenceIsStillStarting() {
        #expect(
            EmbeddedBackendService.spawnWaitStep(
                readiness: .notResponding, exitDiagnosis: nil, elapsed: 30
            ) == .keepWaiting
        )
    }

    // MARK: - The four conditions the old code flattened into "never served"

    /// Daniel's Dev Embedded launch: nineteen `GET /api/registry 401` while the
    /// app reported "The engine started but never began serving after 5 minutes."
    /// A 401 is a credential rejection, and the app HAD the status code.
    @Test("a serving engine that rejects our token is not 'never served'")
    func credentialRejectionIsItsOwnVerdict() {
        #expect(
            EmbeddedBackendService.spawnWaitStep(
                readiness: .authRejected,
                exitDiagnosis: nil,
                elapsed: EmbeddedBackendService.credentialRejectionGrace
            ) == .credentialRejected
        )
        let text = EmbeddedBackendService.credentialRejectedDiagnosis()
        #expect(text.contains("rejected"))
        #expect(!text.lowercased().contains("never began serving"))
        #expect(!text.lowercased().contains("never served"))
    }

    /// A rejection inside the grace window is still startup — the app must not
    /// trade a five-minute lie for a one-second one.
    @Test("a rejection inside the grace window is still startup")
    func credentialRejectionHonoursGrace() {
        #expect(
            EmbeddedBackendService.spawnWaitStep(
                readiness: .authRejected, exitDiagnosis: nil, elapsed: 0
            ) == .keepWaiting
        )
        #expect(EmbeddedBackendService.credentialRejectionGrace < EmbeddedBackendService.spawnedEngineInsanityCap)
    }

    /// `expectedLaunchNonce` exists precisely so readiness can prove the responder
    /// is our child. When it does not match, the app KNOWS another engine holds
    /// the socket — and waiting out the cap cannot change that.
    @Test("a foreign engine on the socket is named, immediately")
    func foreignEngineIsNamedImmediately() {
        #expect(
            EmbeddedBackendService.spawnWaitStep(
                readiness: .identityMismatch(pid: 4242),
                exitDiagnosis: nil,
                elapsed: 0.1
            ) == .foreignEngineServing(pid: 4242)
        )
        let text = EmbeddedBackendService.foreignEngineDiagnosis(pid: 4242)
        #expect(text.contains("4242"), "the PID we were given must reach the user")
        #expect(text.contains("Another engine is already serving"))
        #expect(!text.lowercased().contains("never began serving"))
    }

    /// A responder that won't tell us its PID still gets the right sentence — the
    /// unknown PID must not degrade the diagnosis to a generic one.
    @Test("a foreign engine with no PID is still reported as foreign")
    func foreignEngineWithoutPID() {
        #expect(
            EmbeddedBackendService.spawnWaitStep(
                readiness: .identityMismatch(pid: nil), exitDiagnosis: nil, elapsed: 0.1
            ) == .foreignEngineServing(pid: nil)
        )
        #expect(EmbeddedBackendService.foreignEngineDiagnosis(pid: nil).contains("Another engine is already serving"))
    }

    /// The cap now means what it says: nothing ever answered. It must point at
    /// the engine log, because that is where the remedy is.
    @Test("the cap diagnosis sends the reader to the engine log")
    func capDiagnosisPointsAtTheLog() {
        let text = EmbeddedBackendService.neverBoundDiagnosis()
        #expect(text.contains("nothing answered on its socket"))
        #expect(text.contains("its last lines follow"))
    }

    /// An unreadable log and an empty log are different facts, and both are
    /// diagnostic. Neither may arrive as an empty string that reads as "no
    /// information available".
    @Test("the log tail always says something")
    func logTailAlwaysExplainsItself() {
        #expect(!EmbeddedBackendService.tailEngineLog(lines: 20).isEmpty)
    }

    /// "It's in the engine log" is only a remedy if the reader can find the
    /// engine log. Under the App Sandbox `.libraryDirectory` resolves into the
    /// CONTAINER, so the live log is not at ~/Library/Logs/Fichero/engine.log —
    /// two people spent an evening reading a stale file in the real home and
    /// concluding the engine wrote nothing, while it was writing into the
    /// container. The message must print the resolved path.
    @Test("the cap diagnosis names the log by its resolved path")
    func capDiagnosisNamesTheResolvedLogPath() {
        let diagnosis = EmbeddedBackendService.neverBoundDiagnosis()
        #expect(diagnosis.contains(EmbeddedBackendService.engineLogURL.path))
        // The path must be the FULL resolved one, not a pretty ~ abbreviation:
        // under the sandbox the container segment is the whole point.
        #expect(!diagnosis.contains("~/Library/Logs"))
    }

    /// The writer and the readers must resolve the SAME file. They had built the
    /// path independently in two files, which is one edit away from the app
    /// tailing a log nothing writes to.
    @Test("the spawn writes the log the diagnostics read")
    func spawnAndDiagnosticsAgreeOnTheLogPath() throws {
        let spawn = try Self.appSource("Services/EmbeddedBackendService+Spawn.swift")
        #expect(
            spawn.contains("Self.engineLogURL"),
            "the spawn must open the shared path, not re-derive its own"
        )
        #expect(
            !spawn.contains("Logs/Fichero/engine.log"),
            "a second literal path in the writer is how the writer and reader drift apart"
        )
    }

    /// Death still outranks every one of the new verdicts.
    @Test("an exit diagnosis outranks a foreign engine and a rejection")
    func exitDiagnosisOutranksTheNewVerdicts() {
        for reading: EngineReadiness in [.authRejected, .identityMismatch(pid: 7)] {
            #expect(
                EmbeddedBackendService.spawnWaitStep(
                    readiness: reading, exitDiagnosis: "The engine exited unexpectedly (code 9).", elapsed: 99
                ) == .engineExited(diagnosis: "The engine exited unexpectedly (code 9).")
            )
        }
    }

    /// Ready still outranks everything, including a stale foreign reading.
    @Test("ready outranks every other verdict")
    func readyOutranksEverything() {
        #expect(
            EmbeddedBackendService.spawnWaitStep(
                readiness: .ready, exitDiagnosis: nil, elapsed: 9_999
            ) == .ready
        )
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
        The engine exited unexpectedly (exit code 1).

        ModuleNotFoundError: No module named 'duckdb'
        """
        let step = EmbeddedBackendService.spawnWaitStep(
            readiness: .notResponding,
            exitDiagnosis: diagnosis,
            elapsed: 2  // two seconds in — nowhere near the cap
        )
        #expect(step == .engineExited(diagnosis: diagnosis))
    }

    /// The termination handler must publish the crash diagnosis immediately during
    /// the supervised spawn wait. If it auto-restarts first, `waitForSpawnedBackend`
    /// sees `.starting`, keeps polling, and the UI loses the specific log tail.
    @Test("startup death is surfaced instead of auto-restarted")
    func startupDeathIsSurfacedInsteadOfAutoRestarted() {
        #expect(
            EmbeddedBackendService.shouldSurfaceUnexpectedExitImmediately(
                status: .starting,
                isStarting: true
            )
        )
        #expect(
            EmbeddedBackendService.shouldSurfaceUnexpectedExitImmediately(
                status: .starting,
                isStarting: false
            )
        )
        #expect(
            !EmbeddedBackendService.shouldSurfaceUnexpectedExitImmediately(
                status: .running,
                isStarting: false
            )
        )
    }

    /// The diagnostic string is exactly what reaches `BackendError.engineDidNotStart`,
    /// then `EngineLifecycleController.showBackendError`, then `EngineSession.phase`.
    /// Keep it specific and tail-bearing — never regress to a generic timeout.
    @Test("unexpected exit diagnosis preserves engine log tail")
    func unexpectedExitDiagnosisPreservesEngineLogTail() {
        let diagnosis = EmbeddedBackendService.unexpectedExitDiagnosis(
            description: "exit code 1",
            tail: "ModuleNotFoundError: No module named 'duckdb'"
        )
        #expect(diagnosis.contains("The engine exited unexpectedly (exit code 1)."))
        #expect(diagnosis.contains("ModuleNotFoundError: No module named 'duckdb'"))
        #expect(!diagnosis.contains("timeout"))

        let surfaced = BackendError.engineDidNotStart(diagnosis: diagnosis).localizedDescription
        #expect(surfaced == diagnosis)
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
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
