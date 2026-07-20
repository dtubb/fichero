import FicheroAPIClient
import Foundation
import OSLog

extension AppState {
    /// Start a background loop that pings `/api/health` every 5s and updates
    /// `isBackendRunning` so the existing "Backend Not Running" UI surfaces
    /// when the engine dies mid-session. Uses a separate quieter ping than
    /// `checkBackendHealth()` so we don't flicker `isCheckingBackend` /
    /// re-fetch providers on every tick. (#967)
    func startBackendHeartbeat() {
        guard heartbeatTask == nil else { return }
        heartbeatTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                if Task.isCancelled { break }
                await self?.pingBackendOnce()
            }
        }
    }

    func reconfigureGeneratedClientsForCurrentHost() {
        ficheroClient.reconfigure(baseURL: EngineConfig.host)
        // The app-wide legacy APIClient (MCPService and other apiClient-based
        // services) holds a SEPARATE FicheroClient — rebind it too (#2349) or it
        // silently keeps talking to the old (localhost) host after a host change.
        apiClient.reconfigure(baseURL: EngineConfig.host)
        NotificationCenter.default.post(name: EngineConfig.engineHostDidChangeNotification, object: nil)
    }

    private func pingBackendOnce() async {
        // Health-200 alone is NOT "online" (#2864): a leftover engine can answer
        // health yet reject our token. The shared readiness probe (#3106) does
        // health + authenticated registry in one, over the pinned transport.
        switch await EngineReadinessProbe(client: ficheroClient).probe() {
        case .ready:
            heartbeatFailureCount = 0
            recordActiveEndpoint()
            if !isBackendRunning {
                engine.markReady()
                logger.info("Backend heartbeat: recovered — back online")
                // Reload providers now that the engine is back so list views
                // aren't empty until next manual refresh.
                await loadProviders()
            }
        case .authRejected:
            heartbeatFailureCount = 0
            engine.markAuthRejected("The engine is running but rejected this app's credentials.")
            logger.warning("Backend heartbeat: auth rejected — flipping authBroken")
        case .notResponding:
            await noteHeartbeatFailure(reason: "engine not responding")
        case .identityMismatch:
            await noteHeartbeatFailure(reason: "engine identity mismatch")
        }
    }

    private func noteHeartbeatFailure(reason: String) async {
        heartbeatFailureCount += 1
        guard heartbeatFailureCount >= offlineFlipThreshold else { return }
        // The active endpoint has stopped answering. Before declaring the paired
        // host unreachable, walk its OTHER known endpoints (LAN → tailnet), each
        // over its own per-endpoint trust and never localhost (#3098). Only when
        // they're all exhausted — or there are none — do we fail closed.
        switch await attemptEndpointFailover() {
        case .recovered, .exhausted:
            // Failover already resolved the phase (ready, or unreachable with a
            // specific "no other endpoint answered" reason) — nothing to add.
            return
        case .noAlternates:
            break // single-endpoint host: fall through to the generic diagnosis.
        }
        if isBackendRunning {
            logger.warning(
                "Backend heartbeat: \(self.heartbeatFailureCount) consecutive failures — flipping offline (\(reason))"
            )
            engine.markUnreachable("""
                Lost connection to the Fichero engine.

                The backend stopped responding mid-session. Restart it with:

                PYTHONPATH=src python -m fichero.api
                """)
        }
    }

    /// Outcome of walking a paired host's alternate endpoints (#3098).
    private enum FailoverOutcome {
        /// An alternate endpoint answered; the app is rebound and `ready`.
        case recovered
        /// Alternates existed but none answered; flipped `unreachable` with a
        /// specific, surfaced reason (never localhost, never silent).
        case exhausted
        /// The active host has no known alternate endpoint — caller fails closed
        /// with its own generic diagnosis (unchanged single-endpoint behaviour).
        case noAlternates
    }

    /// When the active endpoint drops, try the paired host's other known
    /// endpoints in failover priority order (#3098). Each candidate is probed
    /// over the shared pinned transport, which resolves trust per endpoint URL —
    /// the LAN endpoint's SPKI pin, the tailnet endpoint's real cert — so a
    /// switch never reuses the wrong trust and never lands on the local engine
    /// (loopback is filtered out of the endpoint set). Surfaces WHY it switched
    /// (`markStarting` + logged reason) so a failover is never a silent dead
    /// connection, and fails closed with a specific reason once alternates run
    /// out.
    private func attemptEndpointFailover() async -> FailoverOutcome {
        let current = BackendHost.appDefault
        // The LOCAL engine dropping means "restart the local engine", not "jump to
        // some previously-paired remote host" — never fail over off loopback.
        guard !current.isLocal else { return .noAlternates }
        guard let paired = PairedHostEndpoints(ordered: PairedHostEndpointStore.endpoints()) else {
            return .noAlternates
        }
        let candidates = paired.failoverCandidates(excluding: current)
        guard !candidates.isEmpty else { return .noAlternates }

        for candidate in candidates {
            engine.markStarting()
            logger.warning(
                "Endpoint failover: \(PairedHostEndpoints.failoverReason(from: current, to: candidate))"
            )
            // A candidate is a DIFFERENT host than the app's current client, so
            // dial it with its own client: the default pinned session resolves the
            // per-URL SPKI trust and AuthTokenMiddleware attaches that host's token.
            switch await EngineReadinessProbe(client: FicheroClient(baseURL: candidate.url)).probe() {
            case .ready:
                commitActiveEndpoint(candidate)
                heartbeatFailureCount = 0
                engine.markReady()
                await loadProviders()
                logger.info(
                    "Endpoint failover recovered on \(candidate.url.host ?? candidate.url.absoluteString)"
                )
                return .recovered
            case .authRejected:
                // Up but rejects this device's token — a per-host auth problem,
                // not an unreachable one. Bind to it and surface that; the other
                // endpoints share the same paired identity and would reject too.
                commitActiveEndpoint(candidate)
                engine.markAuthRejected(
                    "\(candidate.url.host ?? "The endpoint") accepted the connection "
                    + "but rejected this device's token."
                )
                return .exhausted
            case .notResponding, .identityMismatch:
                continue // this endpoint didn't answer — try the next one.
            }
        }

        // Walked every alternate; none answered. Fail closed with a specific,
        // surfaced reason — never localhost, never a silent dead connection.
        engine.markUnreachable(
            PairedHostEndpoints.exhaustedReason(lastTried: candidates[candidates.count - 1])
        )
        return .exhausted
    }

    /// Point the app at `host` and rebind every client to it. The endpoint's
    /// SPKI pin is persisted per URL, so the rebuilt pinned transport enforces
    /// the RIGHT trust for wherever we landed (#3098).
    private func commitActiveEndpoint(_ host: BackendHost) {
        host.persistPinIfNeeded()
        UserDefaults.standard.set(host.url.absoluteString, forKey: EngineConfig.userDefaultsKey)
        reconfigureGeneratedClientsForCurrentHost()
        PairedHostEndpointStore.record(host.url)
    }
}
