import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

private let probeLogger = Logger(subsystem: "app.fichero.fichero", category: "EngineReadinessProbe")

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
            probeLogger.info(
                "readiness legs: health=\(healthCode, privacy: .public) → authRejected (engine reachable, credentials rejected)"
            )
            return .authRejected
        }
        guard health.status == 200 else {
            let healthCode = health.status.map(String.init) ?? "nil (transport error)"
            probeLogger.info(
                "readiness legs: health=\(healthCode, privacy: .public) → notResponding (registry not attempted)"
            )
            return .notResponding
        }
        if let expectedNonce, health.nonce != expectedNonce {
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
        probeLogger.info(
            "readiness legs: health=200 registry=\(registryCode, privacy: .public) → \(resultDescription, privacy: .public)"
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
