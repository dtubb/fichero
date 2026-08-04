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
    /// the `ConnectionPresentation.failureTitle` pattern (#3341).
    enum SpawnWaitStep: Equatable {
        case ready
        case keepWaiting
        /// The child exited; `diagnosis` is the terminationHandler's reason + log tail.
        case engineExited(diagnosis: String)
        /// Health answered 200 but echoed a launch nonce that is not the one we
        /// minted for this spawn: a process we did NOT launch already holds the
        /// socket. `pid` is the responder's, when it told us.
        case foreignEngineServing(pid: Int?)
        /// The engine on this socket is serving and REJECTING our credential
        /// (401/403). It started; it does not accept our token.
        case credentialRejected
        /// Nothing ever answered on the socket before the insanity cap.
        case neverBecameReady
    }

    /// How long a 401/403 may persist before it is reported as a rejection
    /// rather than as startup. Short: the child adopts `FICHERO_BOOTSTRAP_TOKEN`
    /// inside its own lifespan, BEFORE it serves, so a rejection that survives
    /// this window is a real rejection, not a race. The grace exists only so an
    /// older engine build that binds before installing its token is not reported
    /// wrongly in its first second.
    static let credentialRejectionGrace: TimeInterval = 10

    /// Every branch below is a DIFFERENT situation with a different remedy, and
    /// the app already holds the evidence that separates them — the launch nonce,
    /// the status code, the child's exit. Collapsing them into "never served"
    /// (which is what this did) sent the user to look for a missing engine while
    /// an engine was answering on the socket. Each condition now reports itself.
    static func spawnWaitStep(
        readiness: EngineReadiness,
        exitDiagnosis: String?,
        elapsed: TimeInterval,
        cap: TimeInterval = spawnedEngineInsanityCap,
        credentialGrace: TimeInterval = credentialRejectionGrace
    ) -> SpawnWaitStep {
        if readiness == .ready { return .ready }
        if let exitDiagnosis { return .engineExited(diagnosis: exitDiagnosis) }
        // Definitive on sight: our child cannot take a socket another process
        // already holds, so more waiting cannot change the answer — it can only
        // delay the truth by the length of the cap.
        if case .identityMismatch(let pid) = readiness { return .foreignEngineServing(pid: pid) }
        // A 401/403 is the engine ANSWERING. "It never started" is false here.
        if readiness == .authRejected, elapsed >= credentialGrace { return .credentialRejected }
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
            case .foreignEngineServing(let pid):
                // Built as one String first: an OSLogMessage is created at the
                // interpolation site and cannot be joined with `+`.
                let holder = "PID \(pid.map(String.init) ?? "unknown")"
                logger.error(
                    "Another engine (\(holder, privacy: .public)) already serves this socket — not our child; not waiting out the cap"
                )
                throw BackendError.engineDidNotStart(diagnosis: Self.foreignEngineDiagnosis(pid: pid))
            case .credentialRejected:
                logger.warning(
                    "Engine on this socket is serving but rejected the app's token — this is a credential failure, not a start-up failure"
                )
                throw BackendError.engineDidNotStart(diagnosis: Self.credentialRejectedDiagnosis())
            case .neverBecameReady:
                logger.error("Engine alive but nothing ever answered on the socket within the insanity cap (#3930)")
                throw BackendError.engineDidNotStart(diagnosis: Self.neverBoundDiagnosis())
            case .keepWaiting:
                break
            }

            try await Task.sleep(for: pollInterval)
            if Date().timeIntervalSince(startTime) > 1 {
                pollInterval = .milliseconds(500)
            }
        }
    }

    /// Nothing ever answered on the socket. The remedy is in `engine.log`, so say
    /// that and carry its tail — the old wording ("started but never began
    /// serving") asserted a start we cannot observe and named no next step.
    /// `internal` so the diagnosis wording is pinned by a test rather than by a
    /// screenshot.
    static func neverBoundDiagnosis() -> String {
        let minutes = Int(spawnedEngineInsanityCap / 60)
        // NAME the log, resolved. Under the App Sandbox this is NOT
        // ~/Library/Logs/Fichero/engine.log — `.libraryDirectory` resolves into
        // the app's container, so the live log sits somewhere no one would
        // think to look. Two people spent this evening reading a stale file in
        // the real home and concluding the engine writes nothing, while it was
        // writing 52 KB into the container. "It's in the engine log" is only a
        // remedy if the reader can find the engine log.
        let base = "The engine Fichero launched is still running, but nothing answered on its socket "
            + "for \(minutes) minutes. Why it never bound is in \(engineLogURL.path); its last lines follow."
        return "\(base)\n\n\(tailEngineLog(lines: 20))"
    }

    /// Health answered, but from a process we did not launch. The user has a
    /// concrete action here (stop the other engine) that "never served" hides.
    static func foreignEngineDiagnosis(pid: Int?) -> String {
        let who = pid.map { " (PID \($0))" } ?? ""
        return "Another engine is already serving on this socket\(who). It is not the engine Fichero "
            + "just launched — it answered with a different launch id — so Fichero cannot take the "
            + "socket over. Quit the other engine (a hand-started start_backend.sh, or another copy "
            + "of Fichero) and try again."
    }

    /// The engine is up and refusing our token. Never report this as a start-up
    /// failure: a 401 during readiness means the engine rejected the credential,
    /// and telling the user to start an engine that is already running is the
    /// exact wrong instruction.
    static func credentialRejectedDiagnosis() -> String {
        "The engine on this socket is running and answering, but it rejected Fichero's token. "
            + "It is not the engine this launch started, or it is still holding an older token. "
            + "Quit that engine so Fichero can start its own, then try again."
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
        // Build the fallback client ONCE and cache it. probeReadiness is polled
        // many times during the readiness wait; creating a fresh FicheroClient
        // (hence a fresh AF_UNIX connection) per poll is unreliable under a slow
        // debug launch — each new UDS connection can fail to establish ("nw…
        // Connection has no local endpoint") even though the engine is up and
        // the app's persistent main client talks to it fine (logs /api/registry
        // 200). A cached client establishes its UDS connection once and every
        // subsequent probe rides it. Also on the app's ACTIVE transport, not a
        // bare HTTPS one, so UDS mode never dials :8765 where nothing listens.
        if readinessClient == nil {
            readinessClient = FicheroClient(baseURL: backendURL, transportMode: EngineConfig.transportMode)
        }
        guard let client = readinessClient else { return .notResponding }
        let result = await EngineReadinessProbe(client: client, expectedNonce: expectedLaunchNonce).probe()
        // Observability (#dev): report EXACTLY what each poll saw, so a failing
        // adopt shows its stage instead of a bare "no engine". `.notResponding`
        // means the probe's own client couldn't reach /api/health (transport/connect
        // failure). `.authRejected` means health 200 but /api/registry 401/403.
        // `.ready` means both 200. If the engine logs /api/registry 200 while this
        // says `.notResponding`, the 200 is a DIFFERENT client and the probe's
        // client is the one failing to connect.
        logger.info("readiness probe result: \(String(describing: result), privacy: .public)")
        return result
    }

    /// Where the spawned engine's stdout AND stderr land. ONE owner: the spawn
    /// opens this file (`+Spawn.swift`) and the diagnostics read it, and the two
    /// had built the same path independently in two files.
    ///
    /// `.libraryDirectory` is CONTAINER-relative under the App Sandbox, so this
    /// resolves to `<container>/Data/Library/Logs/Fichero/engine.log`, not the
    /// real `~/Library/Logs/…`. That is correct — it is where the sandboxed
    /// child can actually write — but it is not where a human looks, which is
    /// why every message that mentions this file prints the resolved path.
    static var engineLogURL: URL {
        FileManager.default
            .urls(for: .libraryDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Logs/Fichero/engine.log")
    }

    /// Last `lines` lines of the engine log, for surfacing a real cause when
    /// the engine dies (#2863).
    ///
    /// Never returns a bare empty string: "the log could not be read", "the log
    /// is empty", and "here are the lines" are three different facts, and the
    /// first two are themselves diagnostic — an engine that wrote NOTHING to a
    /// log the app wired to its stdout+stderr did not get as far as importing.
    /// Collapsing an unreadable log onto an absent one is how a launch failure
    /// arrives with no cause attached.
    ///
    /// Deliberately OUTSIDE `#if os(macOS)`: this is FileManager + String and
    /// needs no macOS API, but `insanityCapDiagnosis()` — which calls it — is
    /// unguarded, and iOS instantiates this class (`FicheroApp_iOS.swift:14`).
    /// While this sat inside the macOS block the iOS build failed with
    /// "Cannot find 'tailEngineLog' in scope", and the green macOS build hid it.
    static func tailEngineLog(lines: Int) -> String {
        let logURL = engineLogURL
        let contents: String
        do {
            contents = try String(contentsOf: logURL, encoding: .utf8)
        } catch {
            return "(could not read \(logURL.path): \(error.localizedDescription))"
        }
        let tail = contents.split(separator: "\n", omittingEmptySubsequences: false).suffix(lines)
        let joined = tail.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        if joined.isEmpty {
            return "(\(logURL.path) is empty — the engine wrote nothing to stdout or stderr.)"
        }
        return joined
    }
}
