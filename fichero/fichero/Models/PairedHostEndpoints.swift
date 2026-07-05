import FicheroAPIClient
import Foundation

/// The endpoints a single paired host can be reached at, in failover order (#3098).
///
/// A paired Mac is often reachable two ways at once: its **LAN** address (a
/// literal IP or `.local` name, served with a self-signed cert that the pairing
/// QR SPKI-pins) AND its **tailnet** `.ts.net` URL (served with Tailscale's real
/// cert, no pin). When the primary endpoint stops answering — laptop left the
/// LAN, Wi-Fi flipped to cellular — the connection should fail *over* to the next
/// known endpoint for the SAME host rather than dying.
///
/// Each endpoint is a full ``BackendHost``, so its transport identity travels
/// with it: the LAN endpoint carries its `spkiPin` (pinning enforced via
/// `RemoteCertificatePinning`), the tailnet endpoint carries none (real cert).
/// Failover therefore applies the RIGHT trust for whichever endpoint it lands on
/// automatically — the pin is keyed on the endpoint URL, never reused across
/// endpoints. Tokens are likewise per-endpoint through `AuthTokenMiddleware`.
///
/// Hard invariant (the reason this is a type and not a bare array): a remote
/// paired host must NEVER fail over to loopback/127.0.0.1 — that would silently
/// talk to *this* machine's engine while claiming to reach the remote one. Any
/// loopback endpoint is structurally filtered out at construction, so no caller
/// can reintroduce it.
struct PairedHostEndpoints: Equatable {
    /// Endpoints in failover priority order, primary first. Guaranteed
    /// loopback-free and de-duplicated by normalized host.
    let endpoints: [BackendHost]

    /// Builds the ordered, loopback-free endpoint list for one paired host.
    ///
    /// `ordered` is the caller's preferred order (primary first). Loopback
    /// endpoints are dropped — never silently substituted — and later duplicates
    /// of the same host are removed so failover can't cycle on one address.
    /// Returns `nil` when nothing survives (e.g. only a loopback was supplied):
    /// there is no honest remote endpoint, so there is no paired host to model.
    init?(ordered: [BackendHost]) {
        var seen = Set<String>()
        var kept: [BackendHost] = []
        for host in ordered {
            // Hard rule: a remote paired host must never resolve to the local
            // engine. A loopback endpoint here is a bug upstream — drop it loudly
            // in the model rather than let failover reach 127.0.0.1.
            guard !Self.isLoopback(host) else { continue }
            let key = Self.normalizedKey(host)
            guard seen.insert(key).inserted else { continue }
            kept.append(host)
        }
        guard !kept.isEmpty else { return nil }
        self.endpoints = kept
    }

    /// The primary endpoint — the first one failover will try.
    var primary: BackendHost { endpoints[0] }

    /// The next endpoint to try after `failed` stopped answering, or `nil` when
    /// `failed` was the last known endpoint (nothing left to fail over to — the
    /// caller must surface an unreachable state, never loop back to primary
    /// silently). An unknown `failed` host yields `nil` too: we don't guess.
    func next(after failed: BackendHost) -> BackendHost? {
        let failedKey = Self.normalizedKey(failed)
        guard let index = endpoints.firstIndex(where: { Self.normalizedKey($0) == failedKey }) else {
            return nil
        }
        let nextIndex = endpoints.index(after: index)
        return endpoints.indices.contains(nextIndex) ? endpoints[nextIndex] : nil
    }

    /// Every OTHER endpoint to try when `current` has stopped answering, in
    /// failover priority order (LAN before tailnet). Unlike ``next(after:)``,
    /// this is order-independent of where `current` sits in the list: a client
    /// paired over the stable tailnet URL can still fail *back* to a faster LAN
    /// endpoint that ranks ahead of it. `current` itself is excluded (by
    /// normalized host, so a trailing-slash variant still matches). The reconnect
    /// loop walks these in order and stops at the first that answers; exhausting
    /// them means fail closed — never localhost, never a silent dead connection.
    func failoverCandidates(excluding current: BackendHost) -> [BackendHost] {
        let currentKey = Self.normalizedKey(current)
        return endpoints.filter { Self.normalizedKey($0) != currentKey }
    }

    /// A human-readable reason for a failover, for surfacing in the connection
    /// UI (fed to `EngineSession.markUnreachable`/`markStarting`) so a switch is
    /// never a silent dead connection. Names both endpoints by host.
    static func failoverReason(from failed: BackendHost, to nextHost: BackendHost) -> String {
        "\(hostLabel(failed)) isn’t responding — trying \(hostLabel(nextHost))."
    }

    /// The diagnosis to show when the LAST endpoint failed and there is nowhere
    /// left to fail over to. Fail closed with a specific cause, never localhost.
    static func exhaustedReason(lastTried: BackendHost) -> String {
        "\(hostLabel(lastTried)) isn’t responding and no other paired endpoint is known."
    }

    // MARK: - Helpers

    private static func hostLabel(_ host: BackendHost) -> String {
        host.url.host ?? host.url.absoluteString
    }

    private static func normalizedKey(_ host: BackendHost) -> String {
        AuthTokenMiddleware.normalizedRemoteHostString(hostString: host.url.absoluteString)
    }

    private static func isLoopback(_ host: BackendHost) -> Bool {
        // `tokenKind == .bootstrap` is the app's own signal that a URL is the
        // loopback/embedded engine (see `BackendHost.init`), so it already
        // captures 127.0.0.1 / ::1 / localhost without re-parsing the URL.
        host.isLocal
    }
}

/// The persisted, ordered set of endpoint URLs the app knows the ACTIVE paired
/// host at (#3098). Backs the reconnect loop's failover walk: pairing seeds it
/// with the paired endpoint, every successful connect records the endpoint it
/// landed on, and `endpoints()` materializes them into ``PairedHostEndpoints``.
///
/// Stores only URL strings — never a secret. Each endpoint's SPKI pin already
/// lives in `RemoteCertificatePinning` keyed by the SAME URL, so
/// ``endpoints()`` reads it back per URL and the right trust travels with the
/// host automatically (loopback self-signed pin for LAN, none for a `.ts.net`
/// real cert). Loopback URLs are refused on the way in — a paired host must
/// never resolve to the local engine.
///
/// Single global list (not keyed): the app pairs to ONE host at a time, so
/// re-pairing resets the set (`clear()` then `record()`), which also prevents a
/// previous Mac's stale endpoints from being walked during failover.
enum PairedHostEndpointStore {
    private static let storageKey = "fichero.paired.endpoints"

    /// Raw stored endpoint URL strings, in failover priority order.
    static func stored() -> [String] {
        UserDefaults.standard.stringArray(forKey: storageKey) ?? []
    }

    /// The failover endpoints as `BackendHost`s, each carrying its own persisted
    /// SPKI pin (nil for a real-cert endpoint) so trust is endpoint-correct.
    static func endpoints() -> [BackendHost] {
        stored().compactMap(URL.init(string:)).map { url in
            BackendHost(
                url: url,
                spkiPin: RemoteCertificatePinning.persistedSPKIPin(hostString: url.absoluteString)
            )
        }
    }

    /// Remember `url` as a known endpoint for the paired host, de-duplicated and
    /// re-sorted into failover priority order (LAN before tailnet). A loopback
    /// URL is refused — failover must never reach the local engine.
    static func record(_ url: URL) {
        guard !BackendHost(url: url).isLocal else { return }
        var list = stored().filter { $0 != url.absoluteString }
        list.append(url.absoluteString)
        UserDefaults.standard.set(prioritized(list), forKey: storageKey)
    }

    /// Forget every endpoint — call when unpairing or switching to a different
    /// paired host so failover never walks a stale host's addresses.
    static func clear() {
        UserDefaults.standard.removeObject(forKey: storageKey)
    }

    /// Stable sort by rank: LAN endpoints (IP / `.local`) ahead of tailnet
    /// (`.ts.net`) ahead of anything else, preserving insertion order within a
    /// rank. LAN-first because it's the faster path when both are reachable.
    private static func prioritized(_ list: [String]) -> [String] {
        list.enumerated()
            .sorted { lhs, rhs in
                let lRank = rank(lhs.element), rRank = rank(rhs.element)
                return lRank == rRank ? lhs.offset < rhs.offset : lRank < rRank
            }
            .map(\.element)
    }

    private static func rank(_ urlString: String) -> Int {
        guard let host = URL(string: urlString)?.host?.lowercased() else { return 2 }
        return host.hasSuffix(".ts.net") ? 1 : 0
    }
}
