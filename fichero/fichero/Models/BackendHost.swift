import FicheroAPIClient
import Foundation

/// Which backend a library talks to (#2866). The app can hold several backends
/// at once — the local embedded engine plus N remote hosts — so each
/// `LibraryReference` carries its own host instead of everything keying off the
/// single global `EngineConfig`. Pairs with the host-aware token lookup in
/// `AuthTokenMiddleware`: a request bound for this host authenticates with this
/// host's credential.
struct BackendHost: Equatable, Hashable, Sendable {
    /// Base URL of the engine (e.g. `https://127.0.0.1:8765`, or a remote host).
    let url: URL
    /// SPKI pin to enforce for this host's TLS, if known. Persisted on use so
    /// `RemoteCertificatePinning` validates this host's cert against it.
    let spkiPin: String?
    /// Which credential store this host authenticates against.
    let tokenKind: TokenKind

    enum TokenKind: String, Sendable, Equatable, Hashable {
        case bootstrap   // loopback / embedded engine → .api-key
        case remote      // remote host → device / session token
    }

    /// `tokenKind` defaults to what the URL implies: a loopback host uses the
    /// bootstrap token, anything else a remote token.
    init(url: URL, spkiPin: String? = nil, tokenKind: TokenKind? = nil) {
        self.url = url
        self.spkiPin = spkiPin
        self.tokenKind = tokenKind
            ?? (AuthTokenMiddleware.prefersLocalhostEngineToken(hostString: url.absoluteString)
                ? .bootstrap : .remote)
    }

    /// The app-global engine (`EngineConfig.host`) — the default for every
    /// existing library until a specific remote host is attached. This is
    /// loopback on Mac and the configured remote on iOS, so the token kind is
    /// DERIVED from the URL rather than assumed bootstrap.
    static var appDefault: BackendHost {
        BackendHost(url: EngineConfig.host)
    }

    /// Whether this host is a loopback / embedded engine (bootstrap token).
    var isLocal: Bool { tokenKind == .bootstrap }

    /// Persist this host's SPKI pin so the pinned session validates its cert.
    /// Idempotent — safe to call on every library open. Keyed on the same
    /// `url.absoluteString` that `RemoteCertificatePinning.shouldEnforcePinning`
    /// reads, so the pin the session enforces matches the one persisted here.
    func persistPinIfNeeded() {
        guard let spkiPin, !spkiPin.isEmpty else { return }
        try? RemoteCertificatePinning.persistHostedBackendSPKIPin(
            spkiPin, hostString: url.absoluteString
        )
    }
}
