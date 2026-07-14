import FicheroAPIClient
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

        XCTAssertEqual(
            AuthTokenMiddleware.remoteTokenAccessibilityValue(hostString: host),
            kSecAttrAccessibleAfterFirstUnlock as String,
            "The device token must be EXPLICITLY kSecAttrAccessibleAfterFirstUnlock. "
            + "With no attribute set it inherits the platform default (#3772)."
        )
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
        XCTAssertEqual(
            AuthTokenMiddleware.remoteTokenAccessibilityValue(hostString: host),
            kSecAttrAccessibleAfterFirstUnlock as String,
            "SecItemUpdate must carry kSecAttrAccessible, or a re-pair reverts the fix."
        )
    }

    /// No token stored → nil, not a crash and not a stale value.
    func testNoTokenYieldsNoAccessibility() {
        XCTAssertNil(AuthTokenMiddleware.remoteTokenAccessibilityValue(hostString: host))
    }
}
