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
