import FicheroAPIClient
import Foundation

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
/// accepted (authenticated `GET /api/registry` 200), over the pinned
/// loopback/HTTPS transport. **Fail-closed:** any transport/TLS error classifies
/// as `.notResponding`, never `.ready`.
///
/// This is the single home for the readiness contract, replacing the three
/// drifting copies it superseded (#3106): `EmbeddedBackendService.probeReadiness`,
/// `AppState.probeAuthenticatedRegistry`, and the broken `checkHealth()` that hit
/// `/health` with no `/api` prefix (→ always 404).
struct EngineReadinessProbe {
    let hostURL: URL
    /// The `FICHERO_LAUNCH_NONCE` we expect `/api/health` to echo. `nil` = we
    /// adopted an external engine (no nonce to match) → identity is skipped.
    let expectedNonce: String?
    private let session: URLSession

    init(
        hostURL: URL,
        expectedNonce: String? = nil,
        session: URLSession = RemoteCertificatePinning.configuredSession()
    ) {
        self.hostURL = hostURL
        self.expectedNonce = expectedNonce
        self.session = session
    }

    /// Always `/api/health` — the fix for the `/health` (missing `/api` → 404) bug.
    var healthURL: URL { hostURL.appendingPathComponent("api/health") }
    /// Authenticated but library-header-free, so it cleanly exercises the token.
    var registryURL: URL { hostURL.appendingPathComponent("api/registry") }

    /// Run one probe. Order: cheapest/most-telling first — health (unauth) proves
    /// the socket is up and identifies the responder; the authenticated registry
    /// call proves the token works. Skips the registry call once health or
    /// identity has already decided the outcome.
    func probe() async -> EngineReadiness {
        let health = await fetchHealth()
        guard health.status == 200 else { return .notResponding }
        if let expectedNonce, health.nonce != expectedNonce {
            return .identityMismatch(pid: health.pid)
        }
        let registryStatus = await fetchRegistryStatus()
        return Self.classify(
            healthStatus: 200,
            healthNonce: health.nonce,
            expectedNonce: expectedNonce,
            enginePid: health.pid,
            registryStatus: registryStatus
        )
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

    // MARK: - Transport (fail-closed)

    /// One `/api/health` observation: status + the two identity fields.
    private struct HealthObservation {
        let status: Int?
        let nonce: String?
        let pid: Int?
    }

    private func fetchHealth() async -> HealthObservation {
        do {
            let (data, response) = try await session.data(from: healthURL)
            let status = (response as? HTTPURLResponse)?.statusCode
            let body = try? JSONDecoder().decode(EngineHealthBody.self, from: data)
            return HealthObservation(status: status, nonce: body?.launchNonce, pid: body?.enginePid)
        } catch {
            return HealthObservation(status: nil, nonce: nil, pid: nil)
        }
    }

    private func fetchRegistryStatus() async -> Int? {
        var request = URLRequest(url: registryURL)
        request.httpMethod = "GET"
        request.addEngineAuth()
        do {
            let (_, response) = try await session.data(for: request)
            return (response as? HTTPURLResponse)?.statusCode
        } catch {
            return nil
        }
    }
}

/// Health-only JSON we care about at readiness time (#2862): the two fields that
/// prove instance identity, decoded raw so we don't depend on the generated
/// client's schema being regenerated for them.
private struct EngineHealthBody: Decodable {
    let launchNonce: String?
    let enginePid: Int?
    enum CodingKeys: String, CodingKey {
        case launchNonce = "launch_nonce"
        case enginePid = "engine_pid"
    }
}
