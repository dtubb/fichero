import Foundation

/// The addresses a pairing link carries (`sharing.link-carries-every-address`, #6431): the chosen one first, then every
/// other address that can work, so a joiner on another network falls back from the `.local` name to the Tailscale name
/// (the joiner already tries them in order, `PairingAddressTry`). Pure, so the three places that compose a link agree.
enum PairingLinkAddresses {
    static let maxAddresses = 3

    /// `chosen`, then the other usable rows' addresses (Tailscale before This network), no repeats.
    static func order(chosen: URL, rows: [AddressRow]) -> [URL] {
        let usable = rows.filter(\.isEnabled).compactMap(\.url)
        let isTailnet = { (url: URL) in url.host?.lowercased().hasSuffix(".ts.net") == true }
        let others = usable.filter(isTailnet) + usable.filter { !isTailnet($0) }
        var seen = Set([chosen.absoluteString])
        var out = [chosen]
        for url in others where seen.insert(url.absoluteString).inserted { out.append(url) }
        return Array(out.prefix(maxAddresses))
    }

    /// The payload for `chosen` with the others as `alt_urls`. nil when the chosen address has no usable pin yet; an
    /// alternate with none is left out. One pin serves them all (the same key whatever the name); a public-CA address
    /// ignores it.
    static func payload(
        chosen: URL, rows: [AddressRow], code: PairingCodeRecord, spkiPin: String, libraryPath: String?
    ) -> PairingQRCodePayload? {
        var pin: String?
        var usable: [URL] = []
        for url in order(chosen: chosen, rows: rows) {
            switch RemoteClientPairing.invitePin(spkiPin, for: url) {
            case .missing: if url == chosen { return nil }
            case .notNeeded: usable.append(url)
            case .pin(let value): pin = pin ?? value; usable.append(url)
            }
        }
        return PairingService.buildQRCodePayload(
            apiRoot: chosen, from: code, spki: pin, libraryPath: libraryPath, alternates: Array(usable.dropFirst()))
    }
}
