import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

private let probeLogger = Logger(subsystem: "app.fichero.fichero", category: "EngineReadinessProbe")

/// #4539: the probe runs on a poll, and logging every green poll at `.info`
/// buried the console under identical "health=200 registry=200 → ready" lines.
/// Only TRANSITIONS are worth a line: not-ready → ready, ready → lost, or a leg
/// changing its answer.
///
/// The first fix demoted the steady line to `.debug` on the assumption that
/// `.debug` is invisible. It is not — `.debug` is not PERSISTED, but it is fully
/// visible in a live `log stream`, which is where these logs are actually read.
/// So the demotion achieved the worst of both: a flood while someone is watching,
/// and nothing at all afterwards when they want to know whether the engine was
/// healthy. A steady state that emits ~600 identical lines per five minutes is
/// not a log, it is a denial of service on the reader.
///
/// A transition log logs transitions. Steady state is SILENT, with one rollup
/// every `steadyRollupInterval` saying how long it has held — at **`.notice`**,
/// because "was the engine healthy at 19:40?" is asked AFTER the fact and only
/// `.notice` and above are persisted. This line said `.info` for one commit,
/// claiming a durability `.info` does not have: the identical mistake the
/// `.debug` bug was made of, one commit later. Transitions are `.notice` for the
/// same reason. One line per five minutes is affordable at that level.
/// Internal, not private: `emission` is the decision this whole type exists to
/// get right, and a `private` one cannot be reached by a test — which is how it
/// shipped with an untested assumption about `.debug` in the first place.
@MainActor
enum ProbeTransitionLog {
    /// One rollup per five minutes. At the probe's 500ms steady-state poll that
    /// is ~600 identical observations collapsed into one line.
    static let steadyRollupInterval: TimeInterval = 300

    static var lastSummary: String?
    /// When the CURRENT summary was first observed — the age the rollup reports.
    static var steadySince: Date?
    /// When we last said anything about the current summary, rollups included.
    static var lastSpokeAt: Date?

    /// What a poll should emit. Pure, so the quiet-in-between and the rollup
    /// cadence are testable without a clock, an engine, or a log stream — the
    /// `spawnWaitStep` pattern.
    enum Emission: Equatable {
        /// The reading changed. `previous` is what it was, or nil on the first.
        case transition(previous: String?)
        /// Unchanged, and it has been long enough to say so once.
        case rollup(held: TimeInterval)
        /// Unchanged and already reported. Say nothing.
        case silent
    }

    static func emission(
        summary: String,
        lastSummary: String?,
        steadySince: Date?,
        lastSpokeAt: Date?,
        now: Date,
        interval: TimeInterval = steadyRollupInterval
    ) -> Emission {
        guard summary == lastSummary else { return .transition(previous: lastSummary) }
        guard let lastSpokeAt, now.timeIntervalSince(lastSpokeAt) >= interval else { return .silent }
        return .rollup(held: now.timeIntervalSince(steadySince ?? lastSpokeAt))
    }

    static func log(_ summary: String, now: Date = Date()) {
        switch emission(
            summary: summary,
            lastSummary: lastSummary,
            steadySince: steadySince,
            lastSpokeAt: lastSpokeAt,
            now: now
        ) {
        case .transition(let previous):
            // One literal: an OSLogMessage is built at the interpolation site and
            // cannot be assembled by concatenation.
            let detail = summary + (previous.map { " (was: \($0))" } ?? "")
            probeLogger.notice("\(detail, privacy: .public)")
            lastSummary = summary
            steadySince = now
            lastSpokeAt = now
        case .rollup(let held):
            let detail = "\(summary) — unchanged for \(Self.describe(held))"
            probeLogger.notice("\(detail, privacy: .public)")
            lastSpokeAt = now
        case .silent:
            break
        }
    }

    /// Whole minutes, or seconds under a minute. The rollup is about duration,
    /// not precision, and "unchanged for 300.0000012s" reads as machine output.
    static func describe(_ interval: TimeInterval) -> String {
        let seconds = Int(interval.rounded())
        return seconds < 60 ? "\(seconds)s" : "\(seconds / 60)m"
    }
}

// MARK: - The one engine readiness probe (#3106)

/// The engine readiness contract (#2862/#2864), verified by ONE implementation.
enum EngineReadiness: Equatable {
    /// Health-200 + instance identity + the token accepted.
    case ready
    /// Health didn't answer 200 (down, TLS mismatch, cold-starting) — or any
    /// transport error. Fail-closed default.
    case notResponding
    /// Health answered 200 but echoed a different launch nonce — the port is held
    /// by a process we did NOT spawn. `pid` is the responder's PID.
    case identityMismatch(pid: Int?)
    /// Health + identity OK, but the authenticated probe was rejected (401/403) —
    /// the engine does not accept the token the app holds (the blank-window-401 cause).
    case authRejected
}

/// The single authenticated readiness probe. "Ready" = `GET /api/health` 200 +
/// instance identity (launch-nonce echo, when we spawned the engine) + the token
/// accepted (authenticated `GET /api/registry` 200), over whatever transport the
/// injected `FicheroClient` dials with. **Fail-closed:** any transport/TLS error
/// classifies as `.notResponding`, never `.ready`.
///
/// The observations are fetched through the generated `FicheroClient` rather than
/// raw `URLSession`, so the probe rides the client's active `ClientTransport` —
/// `.https`, in-memory, or a UDS `AF_UNIX` socket — and its `AuthTokenMiddleware`
/// attaches the token automatically. A UDS-only engine (which never answers a raw
/// `hostURL` URLSession request) therefore reports ready here, where the old raw
/// probe was the last blocker for a UDS launch.
///
/// This is the single home for the readiness contract, replacing the three
/// drifting copies it superseded (#3106): `EmbeddedBackendService.probeReadiness`,
/// `AppState.probeAuthenticatedRegistry`, and the broken `checkHealth()` that hit
/// `/health` with no `/api` prefix (→ always 404).
struct EngineReadinessProbe {
    /// The app's generated client. Its operations carry the auth middleware and
    /// the active transport (UDS / in-memory / HTTPS), so the probe works over
    /// whatever transport the client was configured with — no UDS special-casing.
    let client: FicheroClient
    /// The `FICHERO_LAUNCH_NONCE` we expect `/api/health` to echo. `nil` = we
    /// adopted an external engine (no nonce to match) → identity is skipped.
    let expectedNonce: String?

    init(client: FicheroClient, expectedNonce: String? = nil) {
        self.client = client
        self.expectedNonce = expectedNonce
    }

    /// Run one probe. Order: cheapest/most-telling first — health (unauth) proves
    /// the socket is up and identifies the responder; the authenticated registry
    /// call proves the token works. Skips the registry call once health or
    /// identity has already decided the outcome.
    @MainActor
    func probe() async -> EngineReadiness {
        let health = await fetchHealth()
        // A 401/403 on health means the engine IS reachable and answering — it is
        // rejecting our credentials, NOT missing. Surfacing that as `.authRejected`
        // (instead of the old `.notResponding`) lets the launch path say "engine
        // reachable but rejected our token" rather than the false "engine isn't
        // running / start it with start_backend.sh". (#dev observability)
        if health.status == 401 || health.status == 403 {
            let healthCode = health.status.map(String.init) ?? "?"
            // A credential rejection is never steady-state noise: it is the one
            // reading the user can act on, and the transition log would demote a
            // repeated rejection to `.debug` where nobody sees it. Log it at
            // warning EVERY poll.
            // One literal — an OSLogMessage cannot be built by concatenation.
            probeLogger.warning(
                "readiness: health=\(healthCode, privacy: .public) → authRejected (engine reachable; it rejected the app's token)"
            )
            return .authRejected
        }
        guard health.status == 200 else {
            let healthCode = health.status.map(String.init) ?? "nil (transport error)"
            ProbeTransitionLog.log(
                "readiness legs: health=\(healthCode) → notResponding (registry not attempted)"
            )
            return .notResponding
        }
        if let expectedNonce, health.nonce != expectedNonce {
            // The responder is NOT the child we launched. Say so, with the PID,
            // rather than letting the caller infer "never started" from silence.
            let who = health.pid.map(String.init) ?? "unknown"
            let echoed = health.nonce ?? "none"
            // Built as one String first: an OSLogMessage cannot be assembled by
            // concatenation, and the whole detail is safe to log publicly.
            let detail = "nonce \(echoed) is not ours (\(expectedNonce)); responder PID \(who)"
            probeLogger.warning(
                "readiness: health=200 but \(detail, privacy: .public) → identityMismatch"
            )
            return .identityMismatch(pid: health.pid)
        }
        let registryStatus = await fetchRegistryObservation().status
        let result = Self.classify(
            healthStatus: 200,
            healthNonce: health.nonce,
            expectedNonce: expectedNonce,
            enginePid: health.pid,
            registryStatus: registryStatus
        )
        let registryCode = registryStatus.map(String.init) ?? "nil (transport error)"
        let resultDescription = String(describing: result)
        ProbeTransitionLog.log(
            "readiness legs: health=200 registry=\(registryCode) → \(resultDescription)"
        )
        return result
    }

    @MainActor
    func authFailure() async -> AccessError? {
        let registry = await fetchRegistryObservation()
        return Self.classifyAuthFailure(statusCode: registry.status, body: registry.body)
    }

    /// Pure classification of a probe's observations → the readiness contract.
    /// The single source of truth; `probe()` feeds it real observations and the
    /// tests feed synthetic ones, so the contract is verified in exactly one place.
    static func classify(
        healthStatus: Int?,
        healthNonce: String?,
        expectedNonce: String?,
        enginePid: Int?,
        registryStatus: Int?
    ) -> EngineReadiness {
        // A reachable engine that rejects our credentials answers health with
        // 401/403 — that is `.authRejected` (reachable, bad token), NOT
        // `.notResponding` (unreachable). Keeping them distinct is what lets the
        // launch path give an honest diagnosis instead of "engine isn't running".
        if healthStatus == 401 || healthStatus == 403 { return .authRejected }
        guard healthStatus == 200 else { return .notResponding }
        if let expectedNonce, healthNonce != expectedNonce {
            return .identityMismatch(pid: enginePid)
        }
        switch registryStatus {
        case 200: return .ready
        case 401, 403: return .authRejected
        default: return .notResponding
        }
    }

    static func classifyAuthFailure(statusCode: Int?, body: Data?) -> AccessError? {
        guard let statusCode else { return nil }
        return AccessError.classify(statusCode: statusCode, body: body)
    }

    // MARK: - Transport (fail-closed)

    /// One `/api/health` observation: status + the two identity fields.
    private struct HealthObservation {
        let status: Int?
        let nonce: String?
        let pid: Int?
    }

    private struct RegistryObservation {
        let status: Int?
        let body: Data?
    }

    /// `GET /api/health` through the generated op (unauthenticated). `.ok` reads
    /// the instance-identity fields off the typed body; any other case or a thrown
    /// transport error is fail-closed — `status: nil` (or the undocumented code),
    /// never a synthesized 200.
    @MainActor
    private func fetchHealth() async -> HealthObservation {
        do {
            let response = try await client.api.healthCheckApiHealthGet(.init())
            switch response {
            case .ok(let okResponse):
                let body = try okResponse.body.json
                return HealthObservation(status: 200, nonce: body.launchNonce, pid: body.enginePid)
            case .unprocessableContent:
                return HealthObservation(status: 422, nonce: nil, pid: nil)
            case .undocumented(let statusCode, _):
                return HealthObservation(status: statusCode, nonce: nil, pid: nil)
            }
        } catch {
            // H1 (Siracusa): don't swallow the cause. A TLS-pin mismatch, a UDS
            // connect failure, a timeout, and a decode failure of a genuine 200
            // all land here — previously all collapsed to a bare "nil" and read
            // to the user as "engine isn't running". Log the real error; still
            // fail-closed to nil so classification stays conservative.
            probeLogger.error("health probe threw (fail-closed to notResponding): \(error, privacy: .public)")
            return HealthObservation(status: nil, nonce: nil, pid: nil)
        }
    }

    /// Authenticated `GET /api/registry` through the generated op. The client's
    /// `AuthTokenMiddleware` attaches the token, so there's no manual auth header.
    /// `.ok` → 200; a 401/403 (or any other non-2xx) arrives as `.undocumented`,
    /// whose status + collected body feed `classifyAuthFailure`. A thrown transport
    /// error is fail-closed (`status: nil`).
    @MainActor
    private func fetchRegistryObservation() async -> RegistryObservation {
        do {
            let response = try await client.api.listKnownLibrariesApiRegistryGet(.init())
            switch response {
            case .ok:
                return RegistryObservation(status: 200, body: nil)
            case .undocumented(let statusCode, let payload):
                return RegistryObservation(status: statusCode, body: await Self.collectBody(payload))
            }
        } catch {
            // H2 (Siracusa): log the thrown cause instead of vanishing it — a
            // transport hiccup on the authenticated leg was indistinguishable
            // from "engine unreachable". Still fail-closed to nil.
            probeLogger.error("registry probe threw (fail-closed to notResponding): \(error, privacy: .public)")
            return RegistryObservation(status: nil, body: nil)
        }
    }

    /// Collect an undocumented response body into raw `Data` so `AccessError`'s
    /// structured-denial decoder (stale-bootstrap-token / device-expired markers)
    /// can inspect it. Bounded so a hostile/huge error body can't be read without
    /// limit.
    private static func collectBody(_ payload: UndocumentedPayload, upTo maxBytes: Int = 64 * 1024) async -> Data? {
        guard let body = payload.body else { return nil }
        return try? await Data(collecting: body, upTo: maxBytes)
    }
}
