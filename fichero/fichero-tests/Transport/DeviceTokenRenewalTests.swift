@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// #3096: proactive device-token renewal. The decision is pure and tested with
/// fixed dates; the atomic-swap / keep-old-on-failure behaviour is tested against
/// an unresolvable host (real code path, no mock) so a failed renew provably
/// leaves the stored token untouched.
// #4024: all cases share one host/keychain key + UserDefaults expiry. Under Swift Testing's
// default concurrency, another async case's `defer cleanup()` deletes both while
// failedRenewKeepsOldToken is still awaiting the (unresolvable) DNS renew, nil-ing its token
// and expiry before it reads them. Serialize the suite so the shared state is deterministic.
// (Production renew is correct — it writes nothing on failure.)
@Suite(.serialized)
@MainActor
struct DeviceTokenRenewalTests {
    // A guaranteed-non-resolving host (RFC 6761 `.invalid`) so the renew call
    // fails fast without a mock. Non-loopback so it routes to remote storage.
    private let host = URL(string: "https://renew-test.invalid:8765")!
    private var hostString: String { host.absoluteString }

    private func cleanup() {
        AuthTokenMiddleware.clearRemoteToken(hostString: hostString)
        DeviceTokenRenewal.clearExpiry(host: hostString)
    }

    // MARK: - shouldRenew boundaries

    @Test func doesNotRenewWhenFarFromExpiry() {
        let now = Date(timeIntervalSince1970: 1_000_000_000)
        let expires = now.addingTimeInterval(DeviceTokenRenewal.renewalWindow + 60)  // just outside window
        #expect(!DeviceTokenRenewal.shouldRenew(expiresAt: expires, now: now))
    }

    @Test func renewsWithinWindow() {
        let now = Date(timeIntervalSince1970: 1_000_000_000)
        let expires = now.addingTimeInterval(DeviceTokenRenewal.renewalWindow - 60)  // just inside window
        #expect(DeviceTokenRenewal.shouldRenew(expiresAt: expires, now: now))
    }

    @Test func renewsExactlyAtWindowBoundary() {
        let now = Date(timeIntervalSince1970: 1_000_000_000)
        let expires = now.addingTimeInterval(DeviceTokenRenewal.renewalWindow)
        #expect(DeviceTokenRenewal.shouldRenew(expiresAt: expires, now: now))
    }

    @Test func renewsWhenAlreadyExpired() {
        // Past expiry still returns true; the renew attempt then fails on the dead
        // token and the expired → re-pair path takes over (never silently stale).
        let now = Date(timeIntervalSince1970: 1_000_000_000)
        #expect(DeviceTokenRenewal.shouldRenew(expiresAt: now.addingTimeInterval(-60), now: now))
    }

    // MARK: - Expiry persistence

    @Test func storeAndReadExpiryRoundTrips() {
        defer { cleanup() }
        let expires = Date(timeIntervalSince1970: 2_000_000_000)
        DeviceTokenRenewal.storeExpiry(expires, host: hostString)
        #expect(DeviceTokenRenewal.storedExpiry(host: hostString) == expires)
        DeviceTokenRenewal.clearExpiry(host: hostString)
        #expect(DeviceTokenRenewal.storedExpiry(host: hostString) == nil)
    }

    // MARK: - renewIfNeeded: no-ops leave the token untouched

    @Test func noOpWhenExpiryUnknown() async {
        defer { cleanup() }
        try? AuthTokenMiddleware.persistRemoteToken("old-token", hostString: hostString)
        DeviceTokenRenewal.clearExpiry(host: hostString)  // unknown expiry
        await DeviceTokenRenewal.renewIfNeeded(host: host)
        #expect(AuthTokenMiddleware.readRemoteTokenForHost(hostString) == "old-token")
    }

    @Test func noOpWhenNotNearExpiry() async {
        defer { cleanup() }
        try? AuthTokenMiddleware.persistRemoteToken("old-token", hostString: hostString)
        // Expiry far in the future → not near → no network attempt, token kept.
        DeviceTokenRenewal.storeExpiry(Date(timeIntervalSinceNow: 3600 * 24 * 60), host: hostString)
        await DeviceTokenRenewal.renewIfNeeded(host: host)
        #expect(AuthTokenMiddleware.readRemoteTokenForHost(hostString) == "old-token")
        #expect(DeviceTokenRenewal.storedExpiry(host: hostString) != nil)
    }

    // MARK: - renewIfNeeded: a failed renew keeps the old token (rollback)

    @Test func failedRenewKeepsOldToken() async {
        defer { cleanup() }
        try? AuthTokenMiddleware.persistRemoteToken("old-token", hostString: hostString)
        let nearExpiry = Date(timeIntervalSinceNow: 60)  // within the renewal window
        DeviceTokenRenewal.storeExpiry(nearExpiry, host: hostString)

        // Host is unresolvable → the renew round-trip throws → the write in the
        // success branch never runs → old token + old expiry are preserved.
        await DeviceTokenRenewal.renewIfNeeded(host: host)

        #expect(AuthTokenMiddleware.readRemoteTokenForHost(hostString) == "old-token")
        // Tolerance, not equality: the expiry round-trips through a Double
        // (timeIntervalSince1970 in UserDefaults), which can shave sub-ms
        // precision off the Date and flake an exact == (seen 2026-07-26).
        let stored = DeviceTokenRenewal.storedExpiry(host: hostString)
        #expect(stored != nil)
        #expect(abs((stored ?? .distantPast).timeIntervalSince(nearExpiry)) < 0.001)
    }
}
