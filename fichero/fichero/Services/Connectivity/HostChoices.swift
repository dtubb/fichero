import Foundation

/// The pure rules for "Mac finds host" (sharing.mac-finds-host, #5734): which discovered
/// Bonjour services are offered, and how a typed name becomes an address. Discovery
/// (NWBrowser on `_fichero._tcp`) only feeds `offered`; the pairing code grants trust.
enum HostChoices {
    struct Found: Equatable, Sendable {
        let name: String
        let publicURL: String?
    }

    /// The Bonjour service name the engine advertises for a Mac (`security/discovery.py`: "Fichero Server on <host>",
    /// dots made dashes), so a Mac can leave itself out of its own list (#5892).
    static func ownServiceName(hostName: String) -> String {
        "Fichero Server on " + hostName.replacingOccurrences(of: ".", with: "-")
    }

    /// The tailnet a `.ts.net` address belongs to: its name without the machine's first label
    /// ("studio.tail1234.ts.net" is on "tail1234.ts.net"); nil for any other address.
    static func tailnet(of urlString: String?) -> String? {
        guard let host = urlString.flatMap({ URL(string: $0)?.host?.lowercased() }), host.hasSuffix(".ts.net") else { return nil }
        let labels = host.split(separator: ".")
        return labels.count >= 4 ? labels.suffix(3).joined(separator: ".") : nil  // machine.tailnet.ts.net
    }

    /// Whether pairing with this host needs its invite link. Bonjour carries no key to pin and nothing that binds a
    /// name to a host (its TXT record is unauthenticated), so the code alone is enough ONLY for a `.ts.net` host in
    /// THIS Mac's own tailnet: a certificate for that name is one only a member of that tailnet holds. Any other host
    /// (another tailnet, a look-alike, a `.local` name) asks for its invite, and a Mac with no tailnet name of its own
    /// asks every host for it (#5892, review 474).
    static func needsInvite(_ host: Found, ownTailnetURL: String?) -> Bool {
        guard let theirs = tailnet(of: host.publicURL), let ours = tailnet(of: ownTailnetURL) else { return true }
        return theirs != ours
    }

    /// Whether a pasted invite's address is the host that was picked (a different one is refused in words).
    static func invite(_ inviteURL: String, isFor host: Found) -> Bool {
        guard let raw = host.publicURL, let want = URL(string: raw)?.host?.lowercased(),
              let got = URL(string: inviteURL)?.host?.lowercased() else { return false }
        return want == got
    }

    /// The sentence that refuses a code or link for another host than the Mac that was picked; nil when it is for the
    /// picked one, or when the picked Mac has no address Bonjour resolved to compare with (#5918).
    ///
    /// Hosts are compared by name, case-insensitively and without a trailing dot ("Studio.local." is "studio.local");
    /// a `.local` name and the same Mac's IP address are different hosts and refuse (it fails closed), which the
    /// sentence says.
    static func refusal(forInviteAt inviteURL: String, picked: Found) -> String? {
        guard let pickedURL = picked.publicURL else { return nil }
        guard sameHost(inviteURL, pickedURL) else {
            return "That code is for another Mac than \(picked.name), or names it by a different address than the one found "
                + "(a .local name and an IP address do not match). Scan the one shown on \(picked.name)."
        }
        return nil
    }

    private static func sameHost(_ a: String, _ b: String) -> Bool {
        func host(_ raw: String) -> String? {
            URL(string: raw)?.host?.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
        }
        guard let left = host(a), let right = host(b) else { return false }
        return left == right
    }

    /// Reachable, secure, not this Mac, one row per address, sorted by name. A `.ts.net` host is offered only in THIS
    /// Mac's own tailnet, whose suffix is read from Tailscale (`ownTailnetURL`, the engine's detected address), never
    /// from Bonjour; with that suffix unknown every `.ts.net` host is left out (review 474).
    static func offered(_ found: [Found], ownName: String, ownTailnetURL: String? = nil) -> [Found] {
        var seen = Set<String>()
        return found
            .filter { $0.name.caseInsensitiveCompare(ownName) != .orderedSame }
            .filter { host in
                guard let theirs = tailnet(of: host.publicURL) else { return !(host.publicURL ?? "").lowercased().contains(".ts.net") }
                return theirs == tailnet(of: ownTailnetURL)
            }
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
        let typed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !typed.isEmpty, !typed.lowercased().hasPrefix("localhost") else { return nil }
        // host[:port] without a dot is a bare name: .local goes on the host, before any port
        var full = typed
        if !typed.contains("://") {
            let colon = typed.firstIndex(of: ":") ?? typed.endIndex
            let host = String(typed[..<colon]), port = String(typed[colon...])
            full = "https://" + (host.contains(".") ? host : host + ".local") + port
        }
        return try? validatedRemoteURL(from: full, allowLocalhost: false, requireSecureTransportForRemote: true)
    }
}
