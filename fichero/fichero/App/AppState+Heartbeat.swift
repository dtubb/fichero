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
                logger.info("Backend heartbeat: recovered — back online")
                // #4359: recovery must run the SAME warm-up as launch —
                // session refresh + identity BEFORE markReady. Flipping
                // ready directly left the session phase at `.checking`,
                // which the old full-window gate rendered as a "Sign In"
                // wall to the loopback owner. (Also reloads providers so
                // list views aren't empty until next manual refresh.)
                await warmContextThenMarkReady()
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

    func noteHeartbeatFailure(reason: String) async {
        heartbeatFailureCount += 1
        // A BUSY engine is not a dead engine (2026-08-09): heavy ingest
        // starves the single event loop, probes exceed their deadline, and
        // this path SIGKILLed the very import it was supervising (Daniel's
        // book import died to our own watchdog, twice). While imports are in
        // flight the flip threshold quadruples (~40s of patience instead of
        // ~10s); a genuinely dead engine still gets restarted, just later.
        let importsRunning = ImportActivityGauge.shared.inFlight > 0
        let effectiveThreshold = importsRunning
            ? offlineFlipThreshold * 4 : offlineFlipThreshold
        if importsRunning, heartbeatFailureCount < effectiveThreshold {
            logger.info(
                """
                Backend heartbeat: probe failed during an in-flight import \
                (\(self.heartbeatFailureCount)/\(effectiveThreshold)) — treating as busy, not dead
                """
            )
        }
        guard heartbeatFailureCount >= effectiveThreshold else { return }
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
        guard isBackendRunning else { return }
        // #4064: the supervised (embedded) engine drop is routed back to the
        // app-scoped lifecycle controller, which reuses the existing spawn
        // supervisor (#2611) to auto-restart with bounded retries + backoff
        // and only surfaces a Retry/Quit modal once those run out. The
        // release/embedded build NEVER tells the user to run the engine by
        // hand; the manual-CLI hint is gated to `.debugExternal` (below).
        switch Self.supervisedDropOutcome(for: EngineConfig.engineProvisioningStrategy()) {
        case .autoRestart:
            if let onDropped = onSupervisedBackendDropped {
                logger.warning(
                    """
                    Backend heartbeat: \(self.heartbeatFailureCount) consecutive failures \
                    — invoking supervised auto-restart (#4064, \(reason))
                    """
                )
                await onDropped()
                return
            }
            // No controller wired (preview / test / inert host): fall through to
            // a generic, dev-command-free diagnosis rather than a dead hook.
            logger.warning(
                "Backend heartbeat: \(self.heartbeatFailureCount) consecutive failures — flipping offline (\(reason))"
            )
            engine.markUnreachable(
                "Lost connection to the Fichero server. The backend stopped responding mid-session."
            )
        case .surfaceDiagnosis(let message):
            logger.warning(
                "Backend heartbeat: \(self.heartbeatFailureCount) consecutive failures — flipping offline (\(reason))"
            )
            engine.markUnreachable(message)
        }
    }

    /// Pure decision for a mid-session backend drop on the active host (#4064).
    /// `.autoRestart` routes the supervised (embedded) engine through the
    /// app-scoped spawn supervisor (bounded retries + backoff, then a Retry/Quit
    /// modal); `.surfaceDiagnosis` carries the message shown otherwise. The
    /// release/embedded build never surfaces a manual CLI here — `.autoRestart`
    /// carries no string at all, and the `.debugExternal` diagnosis is the only
    /// one that keeps the dev hint (the dev path runs the engine by hand).
    /// Pure so the release-vs-debug gating is unit-testable without an engine.
    static func supervisedDropOutcome(
        for strategy: EngineConfig.EngineProvisioningStrategy
    ) -> SupervisedDropOutcome {
        switch strategy {
        case .releaseEmbedded:
            return .autoRestart
        case .debugExternal:
            return .surfaceDiagnosis("""
                Lost connection to the Fichero server.

                The backend stopped responding mid-session. Restart it with:

                PYTHONPATH=src python -m fichero_server.api
                """)
        case .configuredRemote, .iosCompanion, .inert:
            return .surfaceDiagnosis(
                "Lost connection to the Fichero server. The backend stopped responding mid-session."
            )
        }
    }

    /// Outcome of a mid-session supervised-engine drop (#4064).
    enum SupervisedDropOutcome: Equatable {
        /// The spawn supervisor should auto-restart the embedded backend
        /// (bounded retries + backoff); no diagnosis is surfaced unless the
        /// retries run out, at which point a Retry/Quit modal is shown.
        case autoRestart
        /// Surface the carried diagnosis immediately (no local process to
        /// respawn). Never contains a manual CLI in the release/embedded path.
        case surfaceDiagnosis(String)
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
                // #4359: same warm-up contract as launch and heartbeat
                // recovery — resolve session + identity BEFORE markReady so
                // the gate phase is never `.checking` behind a ready engine.
                await warmContextThenMarkReady()
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
        // EngineConfig.defaults, NOT .standard: every reader of this key goes
        // through the #4221 seam, and a .standard write here is the exact
        // clobber-the-developer's-real-prefs bug the seam exists to prevent
        // (rollbackFailedHostSwitch's sibling, missed in the first sweep).
        EngineConfig.defaults.set(host.url.absoluteString, forKey: EngineConfig.userDefaultsKey)
        reconfigureGeneratedClientsForCurrentHost()
        PairedHostEndpointStore.record(host.url)
    }
}
