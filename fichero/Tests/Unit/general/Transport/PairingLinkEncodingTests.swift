@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `sharing.qr-drawn-once-per-payload` (docs/contributor_manual/specs/source/sharing-two-macs.md §10.2), the encoding half:
/// the link's JSON has sorted keys, so two copies of one link are byte-identical from any launch of the app on any Mac
/// (JSONEncoder orders keys per process otherwise: three launches of a six-key payload gave three orders, 2026-10-31),
/// and the QR's bytes are the link's. Written 2026-10-31, not yet built (no Xcode run on this Mac).
@MainActor
struct PairingLinkEncodingTests {
    private func payload(library: String? = "/tmp/p/Project.fichero") -> PairingQRCodePayload {
        PairingService.buildQRCodePayload(
            apiRoot: URL(string: "https://macbook-air-m1.local:8765")!,
            from: PairingCodeRecord(code: "TEST-CODE", expiresAt: Date(timeIntervalSince1970: 1_800_000_000)),
            spki: Data("spki-value".utf8).base64EncodedString(),
            libraryPath: library)
    }

    private func json(ofLink link: String) throws -> String {
        let query = URLComponents(string: link)?.queryItems?.first { $0.name == "payload" }?.value
        // One #require per statement: nesting them is a "recursive expansion of macro 'require'" compile error.
        let encoded = try #require(query?.removingPercentEncoding)
        let data = try #require(Data(base64Encoded: encoded))
        return try #require(String(data: data, encoding: .utf8))
    }

    @Test("the link's keys are sorted, so the same payload reads the same everywhere")
    func keysAreSorted() throws {
        let text = try json(ofLink: try RemoteClientPairing.inviteLinkString(from: payload()))
        let keys = try #require(try JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any]).keys.sorted()
        #expect(keys == ["api_url", "expires_at", "library_path", "pair_code", "spki", "v"])
        // the order in the TEXT is the sorted one, not whatever this process chose
        let positions = keys.map { text.range(of: "\"\($0)\"")!.lowerBound }
        #expect(positions == positions.sorted())
    }

    @Test("two encodes of one payload are the same bytes; an absent library leaves its key out")
    func stableAndSparse() throws {
        let first = try RemoteClientPairing.inviteLinkString(from: payload())
        let second = try RemoteClientPairing.inviteLinkString(from: payload())
        #expect(first == second)
        let bare = try json(ofLink: try RemoteClientPairing.inviteLinkString(from: payload(library: nil)))
        #expect(!bare.contains("library_path"))
    }

    @Test("the link still round-trips through the client's own reader")
    func roundTrips() throws {
        let link = try RemoteClientPairing.inviteLinkString(from: payload())
        let fields = try RemoteClientPairing.pairingFields(fromInviteOrPayload: link)
        #expect(fields.pairCode == "TEST-CODE")
        #expect(fields.remoteURL.hasPrefix("https://macbook-air-m1.local:8765"))
    }
}
