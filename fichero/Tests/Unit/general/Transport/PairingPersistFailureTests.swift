@testable import Fichero
@testable import FicheroAPIClient
import Foundation
import Testing

/// `sharing.failed-save-spends-nothing` (docs/contributor_manual/specs/source/sharing-two-macs.md §10.3): the host spends
/// the code and makes the device BEFORE it answers, so a token the Keychain refuses must not leave a ghost device on the
/// host or a bare OSStatus in front of the person. Written 2026-10-31, not yet built (no Xcode run on this Mac).
@MainActor
@Suite(.serialized)
struct PairingPersistFailureTests {
    private let host = URL(string: "https://macbook-air-m1.tail1234.ts.net:8765")!
    private var result: PairingExchangeResult {
        PairingExchangeResult(apiRoot: host, deviceToken: "unsaved-device-token", expiresAt: Date(timeIntervalSinceNow: 3600))
    }

    @Test("a refused save asks the host to revoke the device it just made, with that very token, then forgets it")
    func refusedSaveRevokes() async throws {
        var revokeSawToken: String?
        await #expect(throws: RemoteClientPairingError.tokenNotSaved) {
            try await RemoteClientPairing.storeTokenOrRevoke(
                result, expectedSPKIPin: nil,
                persist: { _, _ in throw AuthTokenStorageError.keychainWriteFailed(-34018) },
                revoke: { _ in
                    // what the middleware would put in the Authorization header for this host, at revoke time
                    revokeSawToken = AuthTokenMiddleware.readTokenFromDisk(hostString: self.host.absoluteString)
                    return true
                })
        }
        #expect(revokeSawToken == "unsaved-device-token")
        #expect(AuthTokenMiddleware.readTokenFromDisk(hostString: host.absoluteString) == nil, "dropped after the one call")
        #expect(AuthTokenMiddleware.readRemoteTokenForHost(host.absoluteString) == nil, "nothing was saved")
    }

    @Test("a saved token asks for no revoke")
    func savedTokenRevokesNothing() async throws {
        var saved: (String, URL)?
        var revoked = false
        try await RemoteClientPairing.storeTokenOrRevoke(
            result, expectedSPKIPin: nil,
            persist: { token, url in saved = (token, url) },
            revoke: { _ in revoked = true; return true })
        #expect(saved?.0 == "unsaved-device-token" && saved?.1 == host)
        #expect(!revoked)
    }

    @Test("the host saying no to the revoke changes nothing for the person: still nothing paired, the same sentence")
    func hostRefusesRevoke() async {
        await #expect(throws: RemoteClientPairingError.tokenNotSaved) {
            try await RemoteClientPairing.storeTokenOrRevoke(
                result, expectedSPKIPin: nil,
                persist: { _, _ in throw AuthTokenStorageError.keychainWriteFailed(-34018) },
                revoke: { _ in false })
        }
    }

    @Test("the sentence names this device, no code, no OSStatus, no 'undocumented'")
    func sentenceIsPlain() {
        let words = RemoteClientPairingError.tokenNotSaved.localizedDescription
        #expect(words.hasPrefix(RemoteClientPairingError.thisDevice))
        #expect(words.contains("Keychain") && words.contains("nothing was paired") && words.contains("new link"))
        for banned in ["34018", "OSStatus", "undocumented", "errSec", "this mac", "this device"] { #expect(!words.contains(banned)) }
        #if os(macOS)
        #expect(RemoteClientPairingError.thisDevice == "This Mac" && words.contains("on this Mac"))
        #else
        #expect(RemoteClientPairingError.thisDevice == "This device" && words.contains("on this device"))
        #endif
    }
}
