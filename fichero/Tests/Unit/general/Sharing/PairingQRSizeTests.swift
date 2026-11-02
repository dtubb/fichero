@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `sharing.ios-qr-payload-size` (Step 1.7): the QR leaves the library path out and stays within 400 encoded characters.
struct PairingQRSizeTests {
    private func payload(alts: [String]) -> PairingQRCodePayload {
        PairingQRCodePayload(version: 1, apiURL: "https://m.tail1234.ts.net:8765", pairCode: "ABCD-1234",
                             expiresAt: Date(timeIntervalSince1970: 1_800_000_000), spki: "c3BraS1waW4=",
                             libraryPath: "/Users/Shared/someone/Library/" + String(repeating: "a", count: 200) + ".fichero", altURLs: alts)
    }

    @Test func theQRFormHasNoLibraryPathAndFits() {
        let form = payload(alts: ["https://m.local:8765", "https://192.0.2.10:8765"]).forQR()
        #expect(form.libraryPath == nil)
        #expect(form.encodedLength <= PairingQRCodePayload.qrCharacterLimit)
        #expect(form.altURLs?.count == 2)
    }

    @Test func addressesAreDroppedFromTheEndNeverTheChosenOne() {
        let many = (0..<3).map { "https://very-long-host-name-number-\($0).example.test.ts.net:8765" }
        let form = payload(alts: many).forQR()
        #expect(form.encodedLength <= PairingQRCodePayload.qrCharacterLimit)
        #expect(form.apiURL == "https://m.tail1234.ts.net:8765")
        #expect((form.altURLs?.count ?? 0) < many.count)
    }
}
