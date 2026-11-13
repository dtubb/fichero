@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `sharing.people.sign-in-without-a-code` (Step 8.9): with accounts on, the share link carries the way to reach the Mac and
/// the project, no code; the guest is asked who they are and signs in with a username and password.
@MainActor
struct SignInWithoutCodeTests {
    private let pin = String(repeating: "A", count: 43) + "="

    @Test func aLinkWithNoCodeAsksWhoThePersonIsBeforeAnythingIsSent() async {
        await #expect(throws: RemoteClientPairingError.personRequired) {
            _ = try await RemoteClientPairing.pairDevice(
                remoteURL: "https://studio.local:8765", pairCode: "", deviceName: "Air", expectedSPKIPin: pin)
        }
        await #expect(throws: RemoteClientPairingError.personRequired) {
            _ = try await RemoteClientPairing.pairAndPersistHost(
                remoteURL: "https://studio.local:8765", pairCode: " ", deviceName: "Air", expectedSPKIPin: pin)
        }
    }

    @Test func aCodelessLinkKeepsTheAddressThePinAndTheProject() throws {
        let payload = PairingQRCodePayload(
            version: 1, apiURL: "https://studio.local:8765", pairCode: "", expiresAt: nil, spki: pin,
            libraryPath: "/Volumes/Archive/Marshall", altURLs: nil)
        let fields = try RemoteClientPairing.pairingFields(
            fromInviteOrPayload: RemoteClientPairing.inviteLinkString(from: payload))
        #expect(fields.pairCode.isEmpty)
        // The link's pin in its canonical form (a 32-byte value reads as a SHA-256 digest, `sha256/…`): the same key.
        #expect(fields.spkiPin == (try RemoteCertificatePinning.validatedSPKIPin(pin)))
        #expect(fields.libraryPath == "/Volumes/Archive/Marshall")
    }

    @Test func theShareSheetSaysToTellThePasswordSeparately() {
        let notes = ShareLibrarySheet.linkNotes(person: "Maya", signsIn: true)
        #expect(notes.contains { $0.contains("username and password") })
        #expect(!notes.contains { $0.contains("single-use code") })
    }

    /// `sharing.multiuser-shares-by-address` (#6568): the project Share sheet, as Add Device, gives the address and an account.
    @Test func atTheTailscaleAddressTheShareSheetNamesConnectAndTheAccount() {
        let notes = ShareLibrarySheet.linkNotes(person: "Maya", atAddress: true)
        #expect(notes.contains { $0.contains("Connect to Another Mac") && $0.contains("username and password") })
        #expect(!notes.contains { $0.contains("link") })
    }
}
