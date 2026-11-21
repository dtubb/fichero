import Foundation

/// `signin.own.mac-writes-the-keychain-item` (#6568): the ONE synchronizable Keychain item a Mac writes so the owner's
/// other devices on the same Apple ID can enrol themselves. Its payload holds the engine id, the Mac's name, its
/// addresses (`.ts.net` first) and the enrollment secret, and nothing else: never the owner key, never a session.
struct OwnDevicesItem: Codable, Equatable {
    struct Address: Codable, Equatable {
        let url: String
        /// The SPKI pin of a `.local` address; nil for a `.ts.net` one (Tailscale's public certificate).
        let spki: String?
    }

    let engineID: String
    let macName: String
    let addresses: [Address]
    let enrollmentSecret: String

    enum CodingKeys: String, CodingKey {
        case engineID = "engine_id"
        case macName = "mac_name"
        case addresses
        case enrollmentSecret = "enrollment_secret"
    }

    /// The addresses as the item keeps them: blanks and repeats dropped, `.ts.net` first, the rest in the order given.
    static func ordered(_ addresses: [Address]) -> [Address] {
        var seen = Set<String>()
        let unique = addresses.filter { !$0.url.isEmpty && seen.insert($0.url).inserted }
        func isTailnet(_ address: Address) -> Bool { URL(string: address.url)?.host?.lowercased().hasSuffix(".ts.net") == true }
        return unique.filter(isTailnet) + unique.filter { !isTailnet($0) }
    }

    /// The item a Mac writes: its tailnet address (no pin, Tailscale's public certificate) and its own address with its
    /// pin. A non-tailnet address with no pin is left out: a phone could not trust it.
    static func make(engineID: String, macName: String, secret: String,
                     tailnetURL: String?, own: Address?) -> OwnDevicesItem {
        var addresses = [Address(url: tailnetURL ?? "", spki: nil)]
        if let own, URL(string: own.url)?.host?.lowercased().hasSuffix(".ts.net") == true {
            addresses.append(Address(url: own.url, spki: nil))
        } else if let own, let pin = own.spki, !pin.isEmpty {
            addresses.append(own)
        }
        return OwnDevicesItem(engineID: engineID, macName: macName, addresses: ordered(addresses), enrollmentSecret: secret)
    }

    func encoded() throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        return try encoder.encode(self)
    }

    static func decode(_ data: Data) throws -> OwnDevicesItem {
        try JSONDecoder().decode(OwnDevicesItem.self, from: data)
    }
}
