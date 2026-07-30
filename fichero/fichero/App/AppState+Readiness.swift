import FicheroAPIClient
import Foundation
import OSLog

extension AppState {
    /// After a health-200, confirm the engine accepts our token, resolve the full
    /// auth context (session + identity), and only THEN flip ready and load
    /// providers — or flip authBroken/unreachable with a diagnosis (#2864). Uses
    /// the one shared readiness probe (#3106). Owning the whole ordering here is
    /// what keeps the first library fetch authorized (#2407): nothing that a
    /// library-scoped request depends on is resolved after `markReady`.
    ///
    /// When `readinessAlreadyProven` is true the spawn wait (#3930) already
    /// established the full readiness contract — health 200 + our launch nonce +
    /// an authenticated `/api/registry` 200 (token accepted). Re-running the probe
    /// here would re-derive that held fact over a fresh pinned-TLS handshake, so
    /// the proven path skips straight to the warm-up (#3975). The un-proven path
    /// (adopt / remote / debug / a transient miss) keeps the full probe + #2864
    /// diagnosis unchanged.
    func confirmAuthAndLoad(readinessAlreadyProven: Bool = false) async {
        if readinessAlreadyProven {
            await warmContextThenMarkReady()
            return
        }
        switch await EngineReadinessProbe(client: ficheroClient).probe() {
        case .ready:
            await warmContextThenMarkReady()
        case .authRejected:
            let accessError = await EngineReadinessProbe(client: ficheroClient).authFailure() ?? .unauthenticated
            backendAccessError = accessError
            engine.markAuthRejected(Self.diagnosis(for: accessError))
            logger.error("Auth rejected on readiness probe — authBroken")
        case .notResponding, .identityMismatch:
            backendAccessError = nil
            engine.markUnreachable(
                "The engine answered health checks but the authenticated readiness probe failed."
            )
        }
    }

    /// Warm the ENTIRE auth context, then flip ready — the #2407 ordering the
    /// first library fetch depends on. The instant `isBackendRunning` becomes true,
    /// `DocumentTabView` mounts the library content and every sub-view `.task`
    /// fires a library-scoped fetch (chains/documents/workflows/conversations/
    /// saved-search). If the restored session and resolved identity aren't in place
    /// first, that first burst races the warm-up and 403s (then 200s on retry). So
    /// resolve them here and make `markReady()` the LAST step — the readiness gate
    /// the first data call awaits, not a blind retry (#2407 preserved).
    ///
    /// Reaching here means an authenticated `/api/registry` already returned 200
    /// (proven by the spawn wait, or by the probe just above), so the bearer token
    /// is on disk and accepted — the explicit `waitForToken` is redundant and gone
    /// (#3975). The session refresh and identity load are independent, so they
    /// overlap instead of running strictly serial (#3975); both still complete
    /// BEFORE `markReady`, so the #2407 first-call-auth-race gate is intact.
    /// Internal (not private): the heartbeat-recovery and endpoint-failover
    /// paths in `AppState+Heartbeat` flip the app back to ready and must run
    /// this SAME warm-up — marking ready without resolving the session phase
    /// left `phase == .checking` behind a true `isBackendRunning`, which is
    /// exactly the state that put a sign-in wall in front of the loopback
    /// owner (#4359).
    func warmContextThenMarkReady() async {
        async let session: Void = sessionStore.refresh()
        async let identity: Void = identityStore.load()
        _ = await (session, identity)
        recordActiveEndpoint()
        backendAccessError = nil
        engine.markReady()
        await loadProviders()
    }

    /// Remember the endpoint the app is currently connected to so failover can
    /// walk back to it later (#3098). No-op for the local engine — loopback is
    /// never a failover target.
    func recordActiveEndpoint() {
        PairedHostEndpointStore.record(EngineConfig.host)
    }

    nonisolated static func diagnosis(for error: AccessError) -> String {
        switch error {
        case .staleBootstrapToken:
            return "Fichero connected to the engine, but this app's saved engine token is "
                + "out of date. Restart the engine and try again."
        case .unauthenticated:
            return "Fichero connected to the engine, but the saved sign-in is out of date. "
                + "Reset Sign-In & Retry."
        case .tlsPinFailure:
            return "This app's pinned certificate doesn't match the running engine. "
                + "Reset the certificate and retry."
        case .deviceAccessExpired:
            return "This device's access has expired. Re-pair it with the engine and try again."
        case .engineUnreachable:
            return "The Fichero server isn't reachable. Start or restart it, then try again."
        case .forbidden(_, let message):
            return message ?? "This app doesn't have access to the running engine."
        case .transport(let description):
            return "Failed to connect to the engine: \(description)"
        }
    }
}
