import Foundation

/// `sharing.ios-local-network-permission` (Step 5.3): iOS asks once before an app touches the local network. If the person
/// declined, a Bonjour browse reports "policy denied" and a direct connect to a LAN address fails with no prompt, so every
/// LAN pairing fails silently. This reads the denial and gives it its sentence. Pure; the sheet and the discovery list draw it.
enum LocalNetworkPolicy {
    /// `kDNSServiceErr_PolicyDenied`, as `NetServiceBrowser` reports it under `NSNetServicesErrorCode`.
    static let deniedCode = -72008

    static let sentence = "Allow Fichero to find devices on your local network: Settings › Fichero › Local Network."
    static let buttonTitle = "Open Settings"

    static func isDenied(errorCode: Int) -> Bool { errorCode == deniedCode }

    /// `.local` names, link-local and the private IPv4 ranges: the addresses only the local network can answer.
    static func isLocalAddress(_ host: String) -> Bool {
        let lowered = host.lowercased()
        if lowered.hasSuffix(".local") || lowered.hasPrefix("169.254.") || lowered.hasPrefix("192.168.") || lowered.hasPrefix("10.") {
            return true
        }
        let parts = lowered.split(separator: ".").compactMap { Int($0) }
        return parts.count == 4 && parts[0] == 172 && (16...31).contains(parts[1])
    }

    /// A failure that reads as the missing permission: no answer or offline from a local address. (A name that did not
    /// resolve is `nameNotFound`, a refusal is the Mac saying no; neither is this.)
    static func explains(_ failure: PairingFailure, host: String) -> Bool {
        (failure == .noAnswer || failure == .offline) && isLocalAddress(host)
    }

    /// The sentence to show for a failed pairing: the permission line where it explains the failure, else the failure's own.
    static func sentence(for failure: PairingFailure, context: PairingFailure.Context) -> String {
        explains(failure, host: context.host) ? sentence : failure.sentence(context)
    }
}
