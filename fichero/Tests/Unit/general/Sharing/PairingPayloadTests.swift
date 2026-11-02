@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `sharing.link-carries-every-address` (Step 1.7): the payload carries the chosen address first and the others as `alt_urls`.
struct PairingPayloadTests {
    private func payload(_ alts: [String]?) -> PairingQRCodePayload {
        PairingQRCodePayload(version: 1, apiURL: "https://m.tail1234.ts.net:8765", pairCode: "ABCD-1234",
                             expiresAt: nil, spki: "c3BraS1waW4=", libraryPath: "/L", altURLs: alts)
    }

    @Test func aNewLinkRoundTripsItsAddressesInOrder() throws {
        let alts = ["https://m.local:8765", "https://192.0.2.10:8765"]
        let link = try RemoteClientPairing.inviteLinkString(from: payload(alts))
        let query = try #require(URLComponents(string: link)?.queryItems?.first { $0.name == "payload" }?.value)
        let json = try #require(Data(base64Encoded: query))
        let text = try #require(String(data: json, encoding: .utf8))
        let decoded = try PairingQRCodePayloadDecoder.decode(message: text)
        #expect(decoded.apiURL == "https://m.tail1234.ts.net:8765")
        #expect(decoded.altURLs == alts)
    }

    @Test func anOldLinkHasNoAddressesAndStillDecodes() throws {
        let old = #"{"v":1,"api_url":"https://m.local:8765","pair_code":"ABCD-1234","spki":"c3BraS1waW4="}"#
        let decoded = try PairingQRCodePayloadDecoder.decode(message: old)
        #expect(decoded.altURLs == nil && decoded.apiURL == "https://m.local:8765")
    }

    @Test func aLinkWithNoAddressesWritesNoKey() throws {
        let link = try RemoteClientPairing.inviteLinkString(from: payload(nil))
        let query = try #require(URLComponents(string: link)?.queryItems?.first { $0.name == "payload" }?.value)
        let data = try #require(Data(base64Encoded: query))
        let json = try #require(String(data: data, encoding: .utf8))
        #expect(!json.contains("alt_urls"))
    }
}
