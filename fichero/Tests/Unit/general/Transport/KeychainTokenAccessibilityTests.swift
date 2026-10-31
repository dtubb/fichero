@testable import FicheroAPIClient
import Security
import XCTest

/// The device token's Keychain protection class (#3772, test-plan §6.1 P0).
///
/// RED before the fix: `persistRemoteToken` set NO `kSecAttrAccessible` anywhere, so
/// the item inherited the platform default. That default (WhenUnlocked) does survive
/// a normal relaunch — so this is not by itself proof of the relaunch bug — but the
/// item is unreadable before first unlock, and trusting an unstated platform default
/// with a security-critical item is the sort of thing that changes under you.
///
/// These read the attribute back OUT of the Keychain, so they assert what was really
/// stored, not what we believe we passed.
final class KeychainTokenAccessibilityTests: XCTestCase {

    private let host = "https://keychain-test.example.local:8765"

    override func setUp() {
        super.setUp()
        AuthTokenMiddleware.clearRemoteToken(hostString: host)
    }

    override func tearDown() {
        AuthTokenMiddleware.clearRemoteToken(hostString: host)
        super.tearDown()
    }

    /// THE ONE THAT MATTERS. A launch before first unlock must still be able to read
    /// the token; a token it cannot read looks exactly like "not paired".
    func testTokenIsStoredWithAfterFirstUnlockAccessibility() throws {
        try AuthTokenMiddleware.persistRemoteToken("device-token-abc", hostString: host)
        #if os(macOS)
        // `sharing.token-saves-on-every-build` (2026-10-31): a Mac token lives in the LOGIN keychain and carries no
        // protection class, because an explicit class routes it to the data-protection keychain, which refused every
        // Developer ID build with errSecMissingEntitlement (-34018).
        XCTAssertNil(AuthTokenMiddleware.remoteTokenAccessibilityValue(hostString: host),
                     "A Mac token carries no protection class: that would route it to the data-protection keychain.")
        #else
        XCTAssertEqual(
            AuthTokenMiddleware.remoteTokenAccessibilityValue(hostString: host),
            kSecAttrAccessibleAfterFirstUnlock as String,
            "The device token must be EXPLICITLY kSecAttrAccessibleAfterFirstUnlock. "
            + "With no attribute set it inherits the platform default (#3772)."
        )
        #endif
    }

    /// `sharing.token-saves-on-every-build`: the ONE query read, write and clear share names the login keychain on a
    /// Mac (no kSecUseDataProtectionKeychain) and the data-protection keychain on iPhone/iPad.
    func testTheRemoteTokenQueryNamesThePlatformsKeychain() {
        let query = AuthTokenMiddleware.remoteTokenKeychainQuery(hostString: host)
        #if os(macOS)
        XCTAssertNil(query[kSecUseDataProtectionKeychain as String])
        XCTAssertFalse(AuthTokenMiddleware.remoteTokenLivesInDataProtectionKeychain)
        #else
        XCTAssertEqual(query[kSecUseDataProtectionKeychain as String] as? Bool, true)
        XCTAssertTrue(AuthTokenMiddleware.remoteTokenLivesInDataProtectionKeychain)
        #endif
        XCTAssertEqual(query[kSecAttrAccount as String] as? String,
                       AuthTokenMiddleware.remoteTokenKeychainAccount(hostString: host))
    }

    /// `sharing.failed-save-spends-nothing`: a token held for one revoke call is read by the middleware before the
    /// Keychain, and gone once dropped.
    func testATransientTokenIsReadOnceAndThenGone() {
        AuthTokenMiddleware.holdTransientRemoteToken("unsaved-token", hostString: host)
        XCTAssertEqual(AuthTokenMiddleware.readTokenFromDisk(hostString: host), "unsaved-token")
        AuthTokenMiddleware.dropTransientRemoteToken(hostString: host)
        XCTAssertNil(AuthTokenMiddleware.readTokenFromDisk(hostString: host))
    }

    /// Not a ThisDeviceOnly variant: those cannot sync, which would foreclose the
    /// zero-touch work later. Pinned so nobody "hardens" it into a corner by accident.
    func testAccessibilityIsNotThisDeviceOnly() throws {
        try AuthTokenMiddleware.persistRemoteToken("device-token-abc", hostString: host)

        let accessible = AuthTokenMiddleware.remoteTokenAccessibilityValue(hostString: host)
        XCTAssertNotEqual(accessible, kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly as String)
        XCTAssertNotEqual(accessible, kSecAttrAccessibleWhenUnlockedThisDeviceOnly as String)
    }

    /// A protection change that quietly breaks the READ would be worse than the bug.
    func testTokenStillRoundTrips() throws {
        try AuthTokenMiddleware.persistRemoteToken("device-token-abc", hostString: host)
        XCTAssertEqual(AuthTokenMiddleware.readRemoteTokenForHost(host), "device-token-abc")
    }

    /// Re-pairing overwrites in place (SecItemUpdate). If the update path dropped the
    /// attribute, the FIRST re-pair after this fix would silently restore the bug.
    func testRepairingKeepsTheAccessibility() throws {
        try AuthTokenMiddleware.persistRemoteToken("first-token", hostString: host)
        try AuthTokenMiddleware.persistRemoteToken("second-token", hostString: host)

        XCTAssertEqual(AuthTokenMiddleware.readRemoteTokenForHost(host), "second-token")
        #if !os(macOS)
        XCTAssertEqual(
            AuthTokenMiddleware.remoteTokenAccessibilityValue(hostString: host),
            kSecAttrAccessibleAfterFirstUnlock as String,
            "SecItemUpdate must carry kSecAttrAccessible, or a re-pair reverts the fix."
        )
        #endif
    }

    /// No token stored → nil, not a crash and not a stale value.
    func testNoTokenYieldsNoAccessibility() {
        XCTAssertNil(AuthTokenMiddleware.remoteTokenAccessibilityValue(hostString: host))
    }
}
