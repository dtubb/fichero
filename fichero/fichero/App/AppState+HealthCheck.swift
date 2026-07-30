import FicheroAPIClient
import Foundation
import OSLog

extension AppState {
    /// Check if the Python API is running
    /// Health-probe with backoff until the engine is ready or the retries run
    /// out — a transient miss while a healthy engine is still finishing startup
    /// must not permanently park the app on "Not Running" (#3162). Backoff is
    /// 1, 2, 3, 4, 5, 5 s (~20 s total): long enough for a slow boot, short
    /// enough to stay responsive.
    /// `provenReadiness` carries the result the spawn wait already established
    /// (#3930) so the first health check can reuse it instead of re-deriving it
    /// (#3975). Only the FIRST attempt reuses it; every backoff retry re-probes
    /// fully — a retry means the fast path didn't land ready, so a stale proof
    /// must never be trusted (#3162).
    func checkBackendHealthUntilReady(maxRetries: Int = 6, provenReadiness: EngineReadiness? = nil) async {
        await checkBackendHealth(provenReadiness: provenReadiness)
        var attempt = 0
        while !isBackendRunning && attempt < maxRetries {
            attempt += 1
            try? await Task.sleep(for: .seconds(Double(min(attempt, 5))))
            if Task.isCancelled { return }
            // Re-derive from scratch on retry (#3162) — never reuse the stale proof.
            await checkBackendHealth()
        }
    }

    /// Whether a readiness result the spawn wait already proved (#3930) lets the
    /// health check skip its redundant re-probe (#3975). Pure so the short-circuit
    /// decision is unit-testable without an engine. Only a fully-proven `.ready`
    /// qualifies — every other value (nil / authRejected / notResponding /
    /// identityMismatch) falls through to the full health probe + #3162 backoff.
    static func shouldReuseProvenReadiness(_ readiness: EngineReadiness?) -> Bool {
        readiness == .ready
    }

    func checkBackendHealth(provenReadiness: EngineReadiness? = nil) async {
        reconfigureGeneratedClientsForCurrentHost()
        LaunchProfile.milestone("checkBackendHealth entry")
        // Enter the checking/starting phase; the outcome below resolves it to
        // ready / unreachable / authBroken (via confirmAuthAndLoad).
        backendAccessError = nil
        engine.markStarting()

        // Fast path (#3975): the spawn wait already proved the FULL readiness
        // contract (health 200 + our launch nonce + authenticated /api/registry
        // 200 = token accepted). Re-running the health GET here AND the
        // authenticated probe inside `confirmAuthAndLoad` would re-derive that same
        // fact over fresh pinned-TLS handshakes — ~3-4 redundant serial round-trips
        // on the launch critical path. Skip both and go straight to the side-effect
        // warm-up + markReady. Anything not proven `.ready` falls through to the
        // full health probe + #3162 backoff below.
        if Self.shouldReuseProvenReadiness(provenReadiness) {
            LaunchProfile.milestone("checkBackendHealth reusing proven readiness (#3975)")
            await confirmAuthAndLoad(readinessAlreadyProven: true)
            return
        }

        LaunchProfile.milestone("checkBackendHealth request-start")
        do {
            let response = try await ficheroClient.api.healthCheckApiHealthGet(headers: .init())
            switch response {
            case .ok(let okResponse):
                let health = try okResponse.body.json
                documentCount = health.activeLibraries ?? 0
                backendVersion = health.backendVersion
                let version = health.backendVersion ?? "unknown"
                let count = health.activeLibraries ?? 0
                logger.info("Backend connected: v\(version), \(count) active libraries")
                // Health 200 is necessary but NOT sufficient (#2864): confirm the
                // engine accepts our token, then — on the ready path —
                // resolve the login gate (#2021/#2022) and identity (F5) BEFORE
                // flipping ready, so the first library fetch is authorized (#2407).
                // `confirmAuthAndLoad` owns that full ordering; the login gate and
                // identity are no longer raced after `markReady`.
                await confirmAuthAndLoad()

            default:
                backendAccessError = nil
                backendVersion = nil
                engine.markUnreachable("API returned error status")
            }

        } catch let error as URLError where error.code == .cannotConnectToHost {
            backendAccessError = .engineUnreachable
            // #4094: an unreachable server's version is unknown — it may have
            // been updated before it comes back. Clearing drops the About
            // window's "Server X" row instead of showing a stale version.
            backendVersion = nil
            // #4064: the manual-CLI hint is a Debug-external-only affordance —
            // the release/embedded build spawns its own engine and must NEVER
            // tell the user to run one by hand. The debug dev runs the engine
            // themselves, so they keep the actionable `PYTHONPATH=src python -m
            // fichero.api` hint; every other strategy gets the generic
            // "couldn't connect" diagnosis.
            engine.markUnreachable(Self.cannotConnectDiagnosis(
                for: EngineConfig.engineProvisioningStrategy()
            ))
            logger.error("Backend not reachable: \(error.localizedDescription)")
        } catch {
            let accessError = AccessError.classify(error)
            backendAccessError = accessError
            backendVersion = nil
            engine.markUnreachable(Self.diagnosis(for: accessError))
            logger.error("Backend health check failed: \(error.localizedDescription)")
        }
    }

    /// Pure: the `cannotConnectToHost` diagnosis for the active provisioning
    /// strategy (#4064). The release/embedded build must NEVER show a manual
    /// CLI — it spawns its own engine — so only `.debugExternal` (the dev
    /// runs the engine by hand) keeps the `PYTHONPATH=src python -m fichero_server.api`
    /// hint. Pure so the release-vs-debug gating is unit-testable without an
    /// engine / AppKit.
    static func cannotConnectDiagnosis(
        for strategy: EngineConfig.EngineProvisioningStrategy
    ) -> String {
        switch strategy {
        case .debugExternal:
            return """
                Cannot connect to API server.

                Please start the API first:

                PYTHONPATH=src python -m fichero_server.api
                """
        case .releaseEmbedded, .configuredRemote, .iosCompanion, .inert:
            return "Cannot connect to the Fichero server. The server didn't come up; try restarting the app."
        }
    }
}
