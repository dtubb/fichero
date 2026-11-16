import CryptoKit
@testable import Fichero
import Foundation
import Testing

/// A typed address's first contact (`sharing.people.sign-in-without-a-code`): the guest's trust alert and the host's pane show
/// the same fingerprint, whatever form the pin is in, and only an address (never a link) takes the typed route.
@MainActor
struct HostKeyFingerprintTests {
    private let spki = Data((0..<91).map { UInt8($0) })

    @Test func bothPinFormsShowTheSameFourGroups() throws {
        let raw = spki.base64EncodedString()
        let hashed = "sha256/" + Data(SHA256.hash(data: spki)).base64EncodedString()
        let shown = try #require(HostKeyFingerprint.text(ofPin: raw))
        #expect(shown == HostKeyFingerprint.text(ofPin: hashed))
        #expect(shown.split(separator: " ").map(\.count) == [4, 4, 4, 4])
        let hex = Data(SHA256.hash(data: spki)).prefix(8).map { String(format: "%02X", $0) }.joined()
        #expect(shown.replacingOccurrences(of: " ", with: "") == hex)
    }

    @Test func noPinShowsNothing() {
        #expect(HostKeyFingerprint.text(ofPin: "") == nil)
    }

    @Test func aTypedAddressIsTheTypedRouteAndALinkIsNot() {
        #expect(HostKeyProbe.typedAddress("10.10.10.1")?.absoluteString == "https://10.10.10.1:8765")
        #expect(HostKeyProbe.typedAddress("https://studio.local:9000")?.absoluteString == "https://studio.local:9000")
        #expect(HostKeyProbe.typedAddress("fichero://pair?payload=abc") == nil)
        #expect(HostKeyProbe.typedAddress("{\"host\":\"x\"}") == nil)
        #expect(HostKeyProbe.typedAddress("http://studio.local:8765") == nil)  // never plain http
        #expect(HostKeyProbe.typedAddress("") == nil)
    }

    @Test func theTrustSentenceSaysWhereToCompareAndWhatADifferentKeyMeans() {
        let words = HostKeyFingerprint.trustSentence(host: "studio.local", fingerprint: "3F2A 91C0 7B44 E1D9")
        #expect(words.contains("3F2A 91C0 7B44 E1D9"))
        #expect(words.contains("Settings › Sharing on studio.local"))
        #expect(words.contains("don't connect"))
    }
}
