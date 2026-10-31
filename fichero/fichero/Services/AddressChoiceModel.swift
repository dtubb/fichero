import Foundation

/// The addresses a host offers in its pairing link and QR, and which one is chosen (`sharing.share-sheet-offers-both-addresses`,
/// #5318). The owner's 2026-10-31 failure: the link named only the `.local` address, which the campus network does not resolve,
/// while the Tailscale address answered. The engine names the addresses (`GET /api/pair/sharing`, `sharing.state-names-every-address`);
/// this only lays them out. The pin follows the row by host (`RemoteClientPairing.invitePin`: `.ts.net` carries none).
enum AddressChoice: String, CaseIterable, Identifiable, Equatable {
    case thisNetwork, tailscale
    var id: String { rawValue }
}

struct AddressRow: Equatable, Identifiable {
    let choice: AddressChoice
    let url: URL
    /// "This network" / "Tailscale".
    let title: String
    /// One line on where the link works.
    let reach: String
    /// Why this row cannot work right now; nil when it can.
    let disabledReason: String?
    var id: AddressChoice { choice }
    var isEnabled: Bool { disabledReason == nil }
}

enum AddressChoiceModel {
    static let thisNetworkReach = "Works only on the same Wi-Fi, when the network lets Macs find each other"
    static let tailscaleReach = "Works anywhere your Tailscale is on"
    static let tailscaleOff = "Tailscale is not running on this Mac"
    static let tailscaleHeld = "Another service holds this port on your tailnet; see Settings › Sharing"
    static let tailscaleNotPublished = "Fichero hasn't published this Mac on your tailnet yet: turn Sharing off and on"

    /// The rows from the engine's sharing state. `sharingAddress` is the address the engine was started with (the one the
    /// link named before); `tailnetURL` the detected `.ts.net` origin (no port); `tailnetForward` "ours" | "foreign" | "none"
    /// (nil for an engine from before the field: treated as "ours" when a tailnet address exists, the old behaviour).
    static func rows(sharingAddress: String, tailnetURL: String?, tailnetForward: String?) -> [AddressRow] {
        var rows: [AddressRow] = []
        let sharing = URL(string: sharingAddress.trimmingCharacters(in: .whitespacesAndNewlines))
        let port = sharing?.port ?? 8765
        if let sharing, let host = sharing.host, !host.lowercased().hasSuffix(".ts.net") {
            rows.append(AddressRow(choice: .thisNetwork, url: sharing, title: "This network", reach: thisNetworkReach, disabledReason: nil))
        }
        let tail = (tailnetURL ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if let tailOrigin = URL(string: tail), let tailHost = tailOrigin.host, tailHost.lowercased().hasSuffix(".ts.net") {
            var parts = URLComponents()
            parts.scheme = "https"
            parts.host = tailHost
            parts.port = tailOrigin.port ?? port
            let reason: String?
            switch tailnetForward {
            case nil, "ours": reason = nil
            case "foreign": reason = tailscaleHeld
            default: reason = tailscaleNotPublished
            }
            if let url = parts.url {
                rows.append(AddressRow(choice: .tailscale, url: url, title: "Tailscale", reach: tailscaleReach, disabledReason: reason))
            }
        } else if sharing != nil {
            // No tailnet address at all: the row is there, greyed, so the person learns what would work across networks.
            if let placeholder = URL(string: "https://tailscale.invalid") {
                rows.append(AddressRow(choice: .tailscale, url: placeholder, title: "Tailscale", reach: tailscaleReach, disabledReason: tailscaleOff))
            }
        }
        return rows
    }

    /// Tailscale when it can work (it was the only address that worked on the campus network), else This network.
    static func defaultChoice(rows: [AddressRow]) -> AddressChoice? {
        if let tail = rows.first(where: { $0.choice == .tailscale && $0.isEnabled }) { return tail.choice }
        return rows.first(where: \.isEnabled)?.choice
    }

    /// The address the link and QR carry for `choice` (the default when nil or when the chosen row is disabled).
    static func root(for choice: AddressChoice?, rows: [AddressRow]) -> URL? {
        if let choice, let row = rows.first(where: { $0.choice == choice && $0.isEnabled }) { return row.url }
        return defaultChoice(rows: rows).flatMap { chosen in rows.first { $0.choice == chosen }?.url }
    }
}
