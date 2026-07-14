import FicheroAPIClient
import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "PairingRestore")

/// Which of the four persisted pairing values survived a relaunch (#3772).
///
/// Pairing does not survive relaunch on iPhone/iPad, and the four values are written
/// by four different mechanisms — so the fix depends entirely on WHICH one is missing,
/// and guessing between them is how you fix the wrong thing:
///
///   token + host survive, PIN missing        → the pinned client cannot be rebuilt
///   host + pin survive, TOKEN missing        → Keychain accessibility / access group
///   token survives, HOST missing/overwritten → EngineConfig candidate ordering clobbers it
///   all four survive, still shows unpaired   → restore is fine; the CONNECTION fails (#3342)
///   token survives but host does NOT         → the ORPHANED-TOKEN case: the Keychain
///                                              outlives an iOS reinstall, UserDefaults
///                                              does not, so a valid token is keyed to a
///                                              host we no longer know
///
/// That last one is not hypothetical here: the token's Keychain ACCOUNT is derived from
/// the saved host (`AuthTokenMiddleware.remoteTokenKeychainAccount` falls back to reading
/// `fichero.engine.host` from UserDefaults). So the token's lookup key DEPENDS on the
/// host — lose the host and a perfectly good token becomes unfindable. The four values
/// are not independent, and this snapshot is what tells us so.
struct PairingRestoreSnapshot: Equatable {
    let host: String?
    let hasToken: Bool
    let tokenAccessibility: String?
    let hasSPKIPin: Bool
    let libraryPath: String?

    var isFullyRestored: Bool {
        host != nil && hasToken && hasSPKIPin
    }

    /// The one fact that identifies the bug. Deliberately blunt.
    var verdict: String {
        if host == nil, hasToken {
            return "ORPHANED TOKEN — a token is stored but the host is gone, so the app "
                + "cannot even look it up (the Keychain account is keyed by host)."
        }
        if host == nil {
            return "HOST MISSING — nothing to reconnect to; the app can only show unpaired."
        }
        if !hasToken {
            return "TOKEN MISSING — host survived but the Keychain read failed "
                + "(accessibility / access group / wrong keychain)."
        }
        if !hasSPKIPin {
            return "PIN MISSING — token and host survived, but the pinned transport "
                + "cannot be rebuilt, so every request fails."
        }
        return "ALL FOUR RESTORED — the restore chain is fine; the CONNECTION is failing "
            + "(see #3342)."
    }
}

enum PairingRestoreDiagnostics {

    /// Read the four persisted values back, exactly as the restore chain would.
    static func snapshot() -> PairingRestoreSnapshot {
        let host = UserDefaults.standard.string(forKey: EngineConfig.userDefaultsKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedHost = (host?.isEmpty == false) ? host : nil

        // Look the token up under the saved host when we have one. When we do NOT,
        // fall back to the ambient lookup — that is what distinguishes "no token" from
        // "token orphaned by a lost host".
        let token = resolvedHost.flatMap { AuthTokenMiddleware.readRemoteTokenForHost($0) }
            ?? AuthTokenMiddleware.readRemoteTokenForHost(EngineConfig.defaultHostString)

        return PairingRestoreSnapshot(
            host: resolvedHost,
            hasToken: token?.isEmpty == false,
            tokenAccessibility: AuthTokenMiddleware.remoteTokenAccessibilityValue(hostString: resolvedHost),
            hasSPKIPin: RemoteCertificatePinning.persistedSPKIPin(hostString: resolvedHost)?.isEmpty == false,
            libraryPath: UserDefaults.standard.string(forKey: RemoteAccessConfig.pairedLibraryPathKey)
        )
    }

    /// Log the snapshot at launch. Secrets are NEVER logged — only whether each value
    /// is present, and the host (which is not a secret; it is on the QR code).
    static func logAtLaunch() {
        let snapshot = snapshot()
        logger.info(
            """
            Pairing restore (#3772): host=\(snapshot.host ?? "MISSING", privacy: .public) \
            token=\(snapshot.hasToken ? "present" : "MISSING", privacy: .public) \
            tokenAccessibility=\(snapshot.tokenAccessibility ?? "none", privacy: .public) \
            pin=\(snapshot.hasSPKIPin ? "present" : "MISSING", privacy: .public) \
            libraryPath=\(snapshot.libraryPath == nil ? "MISSING" : "present", privacy: .public)
            """
        )
        logger.info("Pairing restore verdict: \(snapshot.verdict, privacy: .public)")
    }
}
