import Foundation

/// The pure rules for "Mac finds host" (sharing.mac-finds-host, #5734): which discovered
/// Bonjour services are offered, and how a typed name becomes an address. Discovery
/// (NWBrowser on `_fichero._tcp`) only feeds `offered`; the pairing code grants trust.
enum HostChoices {
    struct Found: Equatable {
        let name: String
        let publicURL: String?
    }

    /// Reachable, secure, not this Mac, one row per address, sorted by name.
    static func offered(_ found: [Found], ownName: String) -> [Found] {
        var seen = Set<String>()
        return found
            .filter { $0.name.caseInsensitiveCompare(ownName) != .orderedSame }
            .compactMap { host -> Found? in
                guard let raw = host.publicURL,
                      let url = try? validatedRemoteURL(
                          from: raw, allowLocalhost: false, requireSecureTransportForRemote: true),
                      seen.insert(url.absoluteString).inserted
                else { return nil }
                return Found(name: host.name, publicURL: url.absoluteString)
            }
            .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    /// "studio", "studio.local" or "studio.local:8443" become https addresses; a full URL is
    /// validated as is. Anything else (blank, loopback, a path) is nil.
    static func typedURL(_ text: String) -> URL? {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty, !t.lowercased().hasPrefix("localhost") else { return nil }
        let full = t.contains("://") ? t : "https://" + (t.contains(".") ? t : t + ".local")
        return try? validatedRemoteURL(from: full, allowLocalhost: false, requireSecureTransportForRemote: true)
    }

    /// A typed host name is a check, not a way in: it must name the host the pasted invite points at,
    /// so a link meant for another Mac is refused before any code is sent. Blank typed text matches.
    static func typedNameMatches(_ typed: String, inviteURL: String) -> Bool {
        if typed.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return true }
        guard let want = typedURL(typed)?.host?.lowercased(),
              let got = URL(string: inviteURL)?.host?.lowercased() else { return false }
        return want == got
    }
}
