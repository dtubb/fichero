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

/// `signin.own.ios-finds-it-and-connects`: the dial. Pure, with the network call passed in, so a test runs it with a fake.
enum OwnDevicesConnect {
    /// The engine said the secret is not (or no longer) valid: the other addresses are the same Mac, so none is tried.
    struct SecretRefused: Error, Equatable {}

    struct Enrolled: Equatable {
        let address: OwnDevicesItem.Address
        let deviceToken: String
        let expiresAt: Date
    }

    enum Failure: LocalizedError, Equatable {
        case noAddress(String)
        case refused(String)
        case noAnswer(String)

        var errorDescription: String? {
            switch self {
            case .noAddress(let mac): "\(mac) did not say where to reach it. Turn the switch off and on again on that Mac."
            case .refused(let mac): "\(mac) no longer lets your devices in by themselves. Turn the switch on again on that Mac."
            case .noAnswer(let mac): "\(mac) did not answer at any of its addresses. Is it awake and on the same Tailscale network?"
            }
        }
    }

    /// A device enrols once: its token is its own, kept in its own Keychain; while one works it never redeems again.
    static func needsEnrolment(engineID: String, hasToken: (String) -> Bool) -> Bool { !hasToken(engineID) }

    /// Dials each address in turn and returns the first that enrols. A refused secret stops at once; any other error moves on.
    static func connect(
        _ item: OwnDevicesItem,
        deviceName: String,
        enroll: (OwnDevicesItem.Address, String, String) async throws -> (token: String, expiresAt: Date)
    ) async throws -> Enrolled {
        let addresses = OwnDevicesItem.ordered(item.addresses)
        guard !addresses.isEmpty else { throw Failure.noAddress(item.macName) }
        for address in addresses {
            do {
                let result = try await enroll(address, item.enrollmentSecret, deviceName)
                return Enrolled(address: address, deviceToken: result.token, expiresAt: result.expiresAt)
            } catch is SecretRefused {
                throw Failure.refused(item.macName)
            } catch {
                continue
            }
        }
        throw Failure.noAnswer(item.macName)
    }
}

/// `signin.own.setting-says-the-trade-off` (#6568): the Mac's switch, its words and where its state is kept.
enum OwnDevicesSwitch {
    static let label = "Sign in my own devices by themselves"
    static let caption = "Any device signed into this Apple ID can open this Mac's libraries without asking. "
        + "Leave it off on a shared Apple ID."
    private static let key = "app.fichero.ownDevices.enabled"

    static func isOn(_ defaults: UserDefaults = .standard) -> Bool { defaults.bool(forKey: key) }
    static func remember(_ enabled: Bool, _ defaults: UserDefaults = .standard) { defaults.set(enabled, forKey: key) }
}
