import FicheroAPIClient
import Foundation
import OSLog

/// Proactive device-token renewal (#3096).
///
/// A paired device holds a Keychain device token that expires (90 days, per
/// #2351) and is never renewed today — after which the device just 401s. This
/// renews it *before* it lapses: on a successful remote connect, if the stored
/// token is within `renewalWindow` of expiry, call `POST /api/pair/devices/renew`
/// over the existing SPKI-pinned transport and swap the Keychain token.
///
/// Fail-closed, no silent fallback (memory: prefer raise over silent fallback):
/// the new token is written to the Keychain **only** on a successful renew, so a
/// failed renew inherently keeps the old token (the required "rollback"). The
/// expired-token path (`AccessError.deviceAccessExpired` → re-pair) is the safety
/// net if renewal never runs (e.g. the device was offline through the window).
///
/// Loopback/bootstrap hosts have no device token and are skipped.
enum DeviceTokenRenewal {
    /// Renew once the token is this close to expiry (14 days).
    static let renewalWindow: TimeInterval = 14 * 24 * 60 * 60

    private static let expiryKeyPrefix = "fichero.device_token_expires_at."
    private static let log = Logger(subsystem: "app.fichero.fichero", category: "DeviceTokenRenewal")

    // MARK: - Pure decision (testable without a clock or network)

    /// Renew when the token expires within `window`. Already-past expiry also
    /// returns `true`; the renew call then fails on the dead token and the
    /// expired → re-pair path takes over (a harmless extra attempt, never a
    /// silent stale state).
    static func shouldRenew(expiresAt: Date, now: Date, window: TimeInterval = renewalWindow) -> Bool {
        expiresAt.timeIntervalSince(now) <= window
    }

    // MARK: - Persisted expiry (per host)

    private static func expiryKey(host: String) -> String {
        expiryKeyPrefix + AuthTokenMiddleware.normalizedRemoteHostString(hostString: host)
    }

    /// Record the token's expiry for a host (called at pair time and after a
    /// successful renew). The token itself lives in the Keychain; only this
    /// non-secret timestamp lives in UserDefaults.
    static func storeExpiry(_ expiresAt: Date, host: String) {
        UserDefaults.standard.set(expiresAt.timeIntervalSince1970, forKey: expiryKey(host: host))
    }

    /// The stored expiry for a host, or nil if unknown (paired before this
    /// feature, or never recorded) — in which case renewal is skipped and the
    /// expired → re-pair path is the safety net.
    static func storedExpiry(host: String) -> Date? {
        let raw = UserDefaults.standard.object(forKey: expiryKey(host: host)) as? Double
        return raw.map { Date(timeIntervalSince1970: $0) }
    }

    static func clearExpiry(host: String) {
        UserDefaults.standard.removeObject(forKey: expiryKey(host: host))
    }

    // MARK: - Renew

    /// Renew the device token for `host` if it is near expiry. No-op for local
    /// hosts, when expiry is unknown, or when it is not yet in the window. On a
    /// successful renew, atomically swaps the Keychain token (written first, the
    /// critical credential) then updates the stored expiry. On any failure the
    /// old token is untouched.
    @MainActor
    static func renewIfNeeded(host: URL, now: Date = Date()) async {
        let hostString = host.absoluteString
        guard let expiresAt = storedExpiry(host: hostString) else { return }
        guard shouldRenew(expiresAt: expiresAt, now: now) else { return }

        do {
            let response = try await renew(host: host)
            // Success → swap. Token first (the credential that must be current),
            // then the expiry timestamp; if the latter somehow failed it would
            // self-heal on the next connect (new token, stale window → renews again).
            try AuthTokenMiddleware.persistRemoteToken(response.deviceToken, hostString: hostString)
            storeExpiry(response.expiresAt, host: hostString)
            log.info("Renewed device token for \(hostString, privacy: .public)")
        } catch {
            // Keep the old token (no write happened) — will retry next connect, or
            // fall through to the expired → re-pair path if it lapses first.
            log.error("Device token renew failed, keeping existing token: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// One renew round-trip over the host's pinned transport. Throws on any
    /// non-200 so the caller keeps the old token.
    @MainActor
    private static func renew(host: URL) async throws -> Components.Schemas.PairResponse {
        let pin = RemoteCertificatePinning.persistedSPKIPin(hostString: host.absoluteString)
        let client = try FicheroClient(baseURL: host, expectedSPKIPin: pin)
        let response = try await client.api.renewDeviceTokenApiPairDevicesRenewPost(.init())
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .undocumented(let statusCode, _):
            throw APIError.httpError(statusCode: statusCode, message: "Device token renew failed")
        }
    }
}
