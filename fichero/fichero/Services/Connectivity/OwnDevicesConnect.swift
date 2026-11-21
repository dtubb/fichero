import Foundation

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
    /// Runs on the caller's actor (`nonisolated(nonsending)`), so the caller's main-actor closure is never sent.
    nonisolated(nonsending) static func connect(
        _ item: OwnDevicesItem,
        deviceName: String,
        enroll: nonisolated(nonsending) (OwnDevicesItem.Address, String, String) async throws -> (token: String, expiresAt: Date)
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
