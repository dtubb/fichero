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
    /// The address the link carries; nil for a placeholder row (Tailscale not detected), which names no host.
    let url: URL?
    /// "This network" / "Tailscale".
    let title: String
    /// One line on where the link works.
    let reach: String
    /// Why this row cannot work right now; nil when it can.
    let disabledReason: String?
    var id: AddressChoice { choice }
    var isEnabled: Bool { disabledReason == nil && url != nil }
    /// The host shown beside the title; nothing for a placeholder.
    var hostText: String? { url?.host }
}

/// A tailnet forward Fichero did not make, and the one command that frees the port (`sharing.stale-forward-says-so`).
struct TailnetServeConflict: Equatable {
    let holds: String
    let freeWith: String

    /// From the engine's `{"holds": ..., "free_with": ...}`; nil when there is none or it is missing either part.
    init?(_ fields: [String: String]?) {
        guard let holds = fields?["holds"], let freeWith = fields?["free_with"] else { return nil }
        self.holds = holds
        self.freeWith = freeWith
    }

    init(holds: String, freeWith: String) {
        self.holds = holds
        self.freeWith = freeWith
    }
}

enum AddressChoiceModel {
    static let thisNetworkReach = "Works only on the same Wi-Fi, when the network lets Macs find each other"
    static let tailscaleReach = "Works anywhere your Tailscale is on"
    static let tailscaleOff = "Tailscale is not running on this Mac"
    static let tailscaleHeld = "Another service holds this port on your tailnet; see Settings › Sharing"
    static let tailscaleNotPublished = "Fichero hasn't published this Mac on your tailnet yet: turn Sharing off and on"
    /// Shown beside the address rows when the Mac has no Tailscale address (`sharing.tailnet-down-says-so`, open question 6).
    static let campusNote = "On a campus or hotel network, Macs often can't see each other. "
        + "If pairing fails, install Tailscale on both and try again."

    /// The foreign-forward reason with the holder and the freeing command named, else the generic line.
    static func heldReason(_ conflict: TailnetServeConflict?, port: Int) -> String {
        guard let conflict else { return tailscaleHeld }
        return "Port \(port) on your tailnet already goes to \(conflict.holds), not to Fichero. "
            + "Run \(conflict.freeWith), then turn Sharing off and on."
    }

    /// Whether the campus note is worth showing: no Tailscale address to offer, so nothing but the local network works.
    static func showsCampusNote(rows: [AddressRow]) -> Bool {
        rows.contains { $0.choice == .tailscale && $0.url == nil }
    }

    /// `tailnet_forward == "unknown"`: a sandboxed engine could not ask Tailscale (#5317). The row is offered, not first.
    static let tailscaleUnchecked = "This build cannot ask Tailscale; see Settings › Sharing"

    /// The rows from the engine's sharing state. `sharingAddress` is the address the engine was started with (the one the
    /// link named before); `tailnetURL` the detected `.ts.net` origin (no port); `tailnetForward` "ours" | "foreign" | "none"
    /// (nil for an engine from before the field: treated as "ours" when a tailnet address exists, the old behaviour).
    static func rows(sharingAddress: String, tailnetURL: String?, tailnetForward: String?,
                     tailnetConflict: TailnetServeConflict? = nil, lanIP: String? = nil) -> [AddressRow] {
        var rows: [AddressRow] = []
        let sharing = URL(string: sharingAddress.trimmingCharacters(in: .whitespacesAndNewlines))
        guard let sharing, let sharingHost = sharing.host else { return rows }
        let port = sharing.port ?? 8765
        if sharingHost.lowercased().hasSuffix(".ts.net") {
            // A `.ts.net` sharer: its own address IS the Tailscale address and works whatever detection says (review M2),
            // unless the engine says no forward of Fichero's reaches it: then the link would name an address that times
            // out, so the row is greyed with why, and the Mac's LAN address is offered instead (the 2026-11-05 Pro: a saved
            // tailnet name with no `:8765` forward).
            let blocked: String? = switch tailnetForward {
            case "foreign": heldReason(tailnetConflict, port: port)
            case "none": tailscaleNotPublished
            default: nil
            }
            rows.append(AddressRow(choice: .tailscale, url: sharing, title: "Tailscale", reach: tailscaleReach, disabledReason: blocked))
            if blocked != nil, let lan = lanIP?.trimmingCharacters(in: .whitespacesAndNewlines), !lan.isEmpty,
               let lanURL = URL(string: "https://\(lan):\(port)") {
                rows.insert(AddressRow(choice: .thisNetwork, url: lanURL, title: "This network", reach: thisNetworkReach,
                                       disabledReason: nil), at: 0)
            }
            return rows
        }
        rows.append(AddressRow(choice: .thisNetwork, url: sharing, title: "This network", reach: thisNetworkReach, disabledReason: nil))
        let tail = (tailnetURL ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if let tailOrigin = URL(string: tail), let tailHost = tailOrigin.host, tailHost.lowercased().hasSuffix(".ts.net") {
            var parts = URLComponents()
            parts.scheme = "https"
            parts.host = tailHost
            parts.port = tailOrigin.port ?? port
            let reason: String?
            var reach = tailscaleReach
            switch tailnetForward {
            case nil, "ours": reason = nil
            case "unknown": reason = nil; reach = tailscaleUnchecked
            case "foreign": reason = heldReason(tailnetConflict, port: parts.port ?? port)
            default: reason = tailscaleNotPublished
            }
            rows.append(AddressRow(choice: .tailscale, url: parts.url, title: "Tailscale", reach: reach, disabledReason: reason))
        } else {
            // No tailnet address: the row is there, greyed and without a host, so the person learns what would work across
            // networks. "unknown" means the engine could not ask Tailscale, not that Tailscale is off.
            let reason = tailnetForward == "unknown" ? tailscaleUnchecked : tailscaleOff
            rows.append(AddressRow(choice: .tailscale, url: nil, title: "Tailscale", reach: tailscaleReach, disabledReason: reason))
        }
        return rows
    }

    /// Tailscale when it can work (it was the only address that worked on the campus network) and the engine saw its own
    /// forward; an unchecked Tailscale row is offered but not first; else This network.
    static func defaultChoice(rows: [AddressRow]) -> AddressChoice? {
        if let tail = rows.first(where: { $0.choice == .tailscale && $0.isEnabled && $0.reach == tailscaleReach }) { return tail.choice }
        return rows.first(where: \.isEnabled)?.choice
    }

    /// The choice the picker shows: the person's, while its row can work; else the default (review L1: a disabled
    /// choice must not leave the control with nothing selected).
    static func shownChoice(_ choice: AddressChoice?, rows: [AddressRow]) -> AddressChoice? {
        if let choice, rows.contains(where: { $0.choice == choice && $0.isEnabled }) { return choice }
        return defaultChoice(rows: rows)
    }

    /// The address the link and QR carry for `choice` (the default when nil or when the chosen row is disabled).
    static func root(for choice: AddressChoice?, rows: [AddressRow]) -> URL? {
        shownChoice(choice, rows: rows).flatMap { chosen in rows.first { $0.choice == chosen }?.url }
    }
}
