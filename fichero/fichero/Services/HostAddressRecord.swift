import Foundation

/// One row of the engine's own address list (`GET /api/pair/addresses`): what the sheet shows beside its two choices.
struct HostAddressRecord: Equatable {
    let url: String
    let listening: Bool
    let label: String?
    let reason: String?

    /// "Tailscale: https://…" for a working address; "Tailscale: not listening — reason" for one that cannot work.
    var line: String {
        let name = (label?.isEmpty == false ? label : nil) ?? url
        if listening { return label?.isEmpty == false ? "\(name): \(url)" : url }
        let why = (reason?.isEmpty == false ? reason : nil) ?? "not available"
        return "\(name) can't be used: \(why)"
    }

    static func lines(_ records: [HostAddressRecord]) -> [String] { records.map(\.line) }
}
