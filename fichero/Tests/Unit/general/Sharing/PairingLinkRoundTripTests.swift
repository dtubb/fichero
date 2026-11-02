@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `sharing.ios-link-opened-from-messages` (Step 5.4): what the host's `inviteLinkString` writes, the phone reads back whole,
/// in the `fichero://` form a tap from Messages opens and in the `https://fichero.app/pair` form a universal link would carry,
/// and the link stays short enough for a message not to wrap or cut it.
struct PairingLinkRoundTripTests {
    private let alts = ["https://m.local:8765", "https://192.0.2.10:8765"]

    private func payload(path: String? = "/Users/Shared/someone/Fichero Projects/Archive.fichero") -> PairingQRCodePayload {
        PairingQRCodePayload(version: 1, apiURL: "https://m.tail1234.ts.net:8765", pairCode: "ABCD-1234",
                             expiresAt: nil, spki: "c3BraS1waW4=", libraryPath: path, altURLs: alts)
    }

    @Test func theCustomSchemeLinkRoundTripsAllThreeAddresses() throws {
        let link = try RemoteClientPairing.inviteLinkString(from: payload())
        #expect(link.hasPrefix("fichero://pair?payload="))
        let fields = try RemoteClientPairing.pairingFields(fromInviteOrPayload: link)
        #expect(fields.remoteURL.hasPrefix("https://m.tail1234.ts.net"))
        #expect(fields.altURLs == alts)
        #expect(fields.pairCode == "ABCD-1234")
    }

    @Test func theUniversalLinkFormCarriesTheSamePayload() throws {
        let link = try RemoteClientPairing.inviteLinkString(from: payload())
        let query = try #require(link.components(separatedBy: "?").last)
        let universal = "https://fichero.app/pair?\(query)"
        let fields = try RemoteClientPairing.pairingFields(fromInviteOrPayload: universal)
        #expect(fields.altURLs == alts && fields.pairCode == "ABCD-1234")
    }

    @Test func aLinkWithThreeAddressesAndALongPathStaysUnderWhatAMessageKeeps() throws {
        let long = "/Users/Shared/someone/Fichero Projects/" + String(repeating: "Archive of letters ", count: 8) + ".fichero"
        let link = try RemoteClientPairing.inviteLinkString(from: payload(path: long))
        #expect(link.count <= 1_500, "a link of \(link.count) characters risks being wrapped or cut (~2000 is the ceiling)")
    }
}
