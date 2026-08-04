import FicheroAPIClient
import Foundation
import Observation
import OSLog
import Security

private let logger = Logger(subsystem: "app.fichero.fichero", category: "EmbeddedBackend")

extension EmbeddedBackendService {
    // MARK: - Token & identity helpers (#2862)

    /// The base environment for the spawned engine: the app's environment with
    /// every inherited `FICHERO_*` key removed (#3933).
    ///
    /// The engine reads `FICHERO_*` to decide auth (`FICHERO_DISABLE_AUTH`) and
    /// its bind surface (`FICHERO_LAN_HOST`, `FICHERO_BIND_HOST`,
    /// `FICHERO_ALLOW_NON_LOOPBACK_BIND`). Those must come only from what the app
    /// sets on the child — not from a stray value in the shell that launched the
    /// app (`FICHERO_DISABLE_AUTH=1 open Fichero.app` must NOT disable auth). All
    /// non-FICHERO vars pass through unchanged so the bundled interpreter still
    /// has PATH/HOME/locale/etc. Pure + static so it is unit-testable without a
    /// running process.
    static func childEnvironmentBase(inheriting inherited: [String: String]) -> [String: String] {
        inherited.filter { !$0.key.hasPrefix("FICHERO_") }
    }

    /// Whether the spawn may pre-write its freshly minted bootstrap token to
    /// `.api-key` (2026-08-04 clobber fix). Only an ABSENT or EMPTY file may
    /// be pre-written: a non-empty file is some engine's live credential —
    /// possibly one this spawn will never replace (external engine holding
    /// the port, child aborting pre-bind) — and overwriting it 401s every
    /// file-reading client of that engine. When the child does start, it
    /// adopts the env token and rewrites the file itself, so skipping the
    /// pre-write costs nothing. Pure and static so the rule is testable
    /// without spawning anything.
    nonisolated static func shouldPreWriteBootstrapTokenFile(at url: URL) -> Bool {
        guard let existing = try? String(contentsOf: url, encoding: .utf8) else {
            return true
        }
        return existing.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// 32 cryptographically-random bytes, base64url without padding — same
    /// shape as the engine's `secrets.token_urlsafe(32)`. Used for both the
    /// bootstrap token and the launch nonce.
    static func generateSecret() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        // M7 (Siracusa): never ignore the RNG status. A failure here would ship a
        // zero/partial-entropy token silently, and every auth would fail with no
        // clue why. A CSPRNG failure is unrecoverable and must be loud.
        let status = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        precondition(
            status == errSecSuccess,
            "SecRandomCopyBytes failed (OSStatus \(status)) — refusing to mint a weak token"
        )
        return Data(bytes).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    /// Write the bootstrap token to `url` with 0600 perms (owner-only), matching
    /// the engine's write. The app is authoritative for the token it minted.
    static func writeBootstrapTokenFile(_ token: String, at url: URL) {
        do {
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try token.data(using: .utf8)?.write(to: url, options: .atomic)
            try FileManager.default.setAttributes(
                [.posixPermissions: 0o600], ofItemAtPath: url.path
            )
        } catch {
            logger.error("Failed to write bootstrap token file: \(error.localizedDescription, privacy: .public)")
        }
    }
}
