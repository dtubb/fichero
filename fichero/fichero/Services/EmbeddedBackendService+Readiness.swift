import FicheroAPIClient
import Foundation
import Observation
import OSLog
import Security

private let logger = Logger(subsystem: "app.fichero.fichero", category: "EmbeddedBackend")

extension EmbeddedBackendService {
    // MARK: - The spawned engine's wait (#3930)

    /// How long a SPAWNED engine may stay alive without ever serving before we
    /// stop believing it. This is an INSANITY cap for a hung process, not a
    /// budget the engine is expected to fit inside: a real cold start is import
    /// + lifespan + bind (~23s measured, and slower on a busy machine or a cold
    /// file cache). Nothing normal should ever come near it.
    static let spawnedEngineInsanityCap: TimeInterval = 300

    /// One step of the spawned-engine wait, as a pure decision (#3930).
    ///
    /// A live child that has not bound yet is NOT a failure — it is startup, and
    /// there is nothing to tell the user and nothing for them to do. Only two
    /// things end the wait early: it served, or it died.
    ///
    /// Order matters: an exit diagnosis beats the cap, so a child that dies at
    /// the cap boundary still reports why it died rather than "never became
    /// ready". Pure so the timing invariants are testable without an engine —
    /// the `BackendConnectionView.connectionFailureTitle` pattern (#3341).
    enum SpawnWaitStep: Equatable {
        case ready
        case keepWaiting
        /// The child exited; `diagnosis` is the terminationHandler's reason + log tail.
        case engineExited(diagnosis: String)
        /// Alive, but never served before the insanity cap.
        case neverBecameReady
    }

    static func spawnWaitStep(
        readiness: EngineReadiness,
        exitDiagnosis: String?,
        elapsed: TimeInterval,
        cap: TimeInterval = spawnedEngineInsanityCap
    ) -> SpawnWaitStep {
        if readiness == .ready { return .ready }
        if let exitDiagnosis { return .engineExited(diagnosis: exitDiagnosis) }
        if elapsed >= cap { return .neverBecameReady }
        return .keepWaiting
    }

    /// Non-nil once the spawned child has exited unexpectedly. The
    /// `terminationHandler` set on the process has already flipped `.failed` and
    /// put the exit code + `engine.log` tail into `errorMessage`, so the reason
    /// is assembled before we ask.
    ///
    /// Read from that handler rather than by polling `kill(pid, 0)`: for OUR OWN
    /// child, `kill(pid, 0)` keeps SUCCEEDING while the process sits as a zombie
    /// awaiting reap, so PID polling can report a dead engine as alive. The
    /// handler fires on reap, which is the moment the truth is knowable.
    private func spawnedEngineExitDiagnosis() -> String? {
        guard status == .failed, let errorMessage, !errorMessage.isEmpty else { return nil }
        return errorMessage
    }

    /// Wait for the engine WE spawned, bounded by its liveness (#3930).
    ///
    /// The old fixed budget made the app race its own engine, and whoever won
    /// decided whether the user saw the app or a failure gate. The engine's cold
    /// start is not something the app can predict, so it stopped guessing.
    // Promoted from `private` to internal: called by spawnAndAdoptEmbeddedEngine
    // in the Lifecycle extension file.
    func waitForSpawnedBackend() async throws {
        // The engine's own startup, as one bar in Instruments. `defer` closes it
        // on every exit, so a launch that fails still renders a bar that ends
        // where it gave up rather than a dangling interval.
        let waitPhase = LaunchProfile.beginPhase("engine startup wait")
        defer { LaunchProfile.endPhase("engine startup wait", waitPhase) }

        let startTime = Date()
        var pollInterval: Duration = .milliseconds(100)
        var markedBound = false

        while true {
            if Task.isCancelled { throw CancellationError() }

            let result = await probeReadiness()
            lastReadiness = result

            // The engine answered health AND echoed our launch nonce: the socket
            // is bound and it is OUR process. Distinct from ready — the token
            // exchange may still be pending — and it is the boundary between
            // "engine starting up" (its import + lifespan) and "app finishing
            // auth", which is the split a launch profile has to show (#3946).
            // `.notResponding` also covers health-200-but-registry-5xx, so this
            // marks the first CONFIRMED bind, never an earlier guess.
            if !markedBound, result != .notResponding {
                markedBound = true
                LaunchProfile.milestone("engine bound (health + identity answered)")
            }

            switch Self.spawnWaitStep(
                readiness: result,
                exitDiagnosis: spawnedEngineExitDiagnosis(),
                elapsed: Date().timeIntervalSince(startTime)
            ) {
            case .ready:
                logger.info("Backend readiness passed (health 200 + identity + authenticated probe)")
                return
            case .engineExited(let diagnosis):
                // Surface the real reason NOW rather than polling a dead process
                // until the cap and then blaming a timeout.
                logger.error("Engine exited during startup — surfacing immediately (#3930)")
                throw BackendError.engineDidNotStart(diagnosis: diagnosis)
            case .neverBecameReady:
                logger.error("Engine alive but never served within the insanity cap (#3930)")
                throw BackendError.engineDidNotStart(diagnosis: Self.insanityCapDiagnosis())
            case .keepWaiting:
                break
            }

            try await Task.sleep(for: pollInterval)
            if Date().timeIntervalSince(startTime) > 1 {
                pollInterval = .milliseconds(500)
            }
        }
    }

    private static func insanityCapDiagnosis() -> String {
        let minutes = Int(spawnedEngineInsanityCap / 60)
        let base = "The engine started but never began serving after \(minutes) minutes."
        let tail = tailEngineLog(lines: 20)
        return tail.isEmpty ? base : "\(base)\n\n\(tail)"
    }

    /// Poll until the engine is genuinely READY (#2862): not just answering
    /// health-200, but the instance we spawned (nonce echo) AND accepting the
    /// app's token (authenticated /api/registry 200). Throws `.timeout` if it
    /// never reaches `.ready`. The last probe result is stored in
    /// `lastReadiness` for #2864's diagnosis.
    ///
    /// The CLOCK-bounded wait, for engines we did not spawn and cannot watch: a
    /// remote host, a dev-run uvicorn, an adopted engine on :8765. There is no
    /// child there, so a timeout is the only honest bound. The engine we spawn
    /// uses `waitForSpawnedBackend()` instead (#3930).
    // Promoted from `private` to internal: called by the adopt* / spawn methods
    // in the Lifecycle extension file.
    func waitForBackend(timeout: TimeInterval) async throws {
        let startTime = Date()
        // Poll aggressively at first (100ms) so we catch the backend as soon as
        // it's ready — local FastAPI typically answers within 200-400ms. Back
        // off to 500ms after the first second to avoid log spam if the backend
        // is genuinely slow/stuck.
        var pollInterval: Duration = .milliseconds(100)
        while Date().timeIntervalSince(startTime) < timeout {
            if Task.isCancelled {
                throw CancellationError()
            }

            let result = await probeReadiness()
            lastReadiness = result
            if result == .ready {
                logger.info("Backend readiness passed (health 200 + identity + authenticated probe)")
                return
            }

            try await Task.sleep(for: pollInterval)
            if Date().timeIntervalSince(startTime) > 1 {
                pollInterval = .milliseconds(500)
            }
        }

        throw BackendError.timeout
    }

    /// One authenticated readiness probe — delegates to the shared
    /// `EngineReadinessProbe` (#3106), the single home for the readiness contract.
    ///
    /// Fetches through the app's `FicheroClient` so the probe uses whatever
    /// transport that client dials (UDS / in-memory / HTTPS), not a raw URLSession
    /// bound to `backendURL`. Falls back to a fresh loopback HTTPS client on the
    /// construction paths (iOS / Settings) that never injected one.
    func probeReadiness() async -> ReadinessResult {
        let client = readinessClient ?? FicheroClient(baseURL: backendURL)
        return await EngineReadinessProbe(client: client, expectedNonce: expectedLaunchNonce).probe()
    }

    /// Last `lines` lines of the engine log, for surfacing a real cause when
    /// the engine dies (#2863). Empty string if the log can't be read.
    ///
    /// Deliberately OUTSIDE `#if os(macOS)`: this is FileManager + String and
    /// needs no macOS API, but `insanityCapDiagnosis()` — which calls it — is
    /// unguarded, and iOS instantiates this class (`FicheroApp_iOS.swift:14`).
    /// While this sat inside the macOS block the iOS build failed with
    /// "Cannot find 'tailEngineLog' in scope", and the green macOS build hid it.
    static func tailEngineLog(lines: Int) -> String {
        let logURL = FileManager.default
            .urls(for: .libraryDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Logs/Fichero/engine.log")
        guard let contents = try? String(contentsOf: logURL, encoding: .utf8) else {
            return ""
        }
        let tail = contents.split(separator: "\n", omittingEmptySubsequences: false).suffix(lines)
        return tail.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
