import FicheroAPIClient
import Foundation
import Observation
import OSLog
#if canImport(AppKit)
import AppKit
#endif
import SwiftUI

enum SettingsTab: Hashable {
    // Per-view settings sections (#3680): one per major view surface.
    case libraryView
    case previewView
    case readerView
    case inspectorView
    case aiModels
    case mcp
    case integrations
    case general
    case engine
    case connect
    case backend
    case users
    case capture
    case about
    case history
    case backups
}

// AppState is the app-state hub (backend session + providers + heartbeat +
// endpoint failover); its body exceeds the default limits. Its private state is
// too coupled to split into a separate-file extension without loosening
// encapsulation, so the hub is kept whole — same precedent as EngineConfig.
// swiftlint:disable file_length type_body_length

/// Global app state including backend connection and provider management
@MainActor
@Observable
class AppState {
    // MARK: - Backend State

    /// The one backend-usability owner (#3107). The five booleans below are now
    /// read-only shims over `engine.phase`, kept under their legacy names so the
    /// ~20 call sites reading `appState.isBackendRunning` (and friends) keep
    /// working while the source of truth lives in `EngineSession`. Both are
    /// `@Observable`, so a view reading `appState.isBackendRunning` transitively
    /// tracks `engine.phase` and re-renders automatically (#2960) — no manual
    /// change forwarding needed.
    let engine = EngineSession()

    /// Every live backend session (#3112) — the loopback engine `engine` plus
    /// any remote hosts, keyed by host. `engine` is seeded as the default
    /// session so `sessions.activeSession === engine` today; the registry is
    /// the seam for connecting to remote Macs at the same time (#2861/#2883).
    @ObservationIgnored lazy var sessions = EngineSessionRegistry(defaultSession: engine)

    /// Engine is up, authenticated, and usable. Backed by `engine.phase == .ready`.
    var isBackendRunning: Bool { engine.isReady }
    /// Engine answers health checks but REJECTS the app's token (HTTP 401/403) —
    /// the state that used to blank the window with silent 401s (#2864).
    var authBroken: Bool { engine.isAuthRejected }
    /// Human-readable cause for the current unreachable/authBroken/failed state
    /// (port occupied by PID / auth rejected / probe failed), shown full-window.
    var backendDiagnosis: String? { engine.diagnosis }
    /// Alias of `backendDiagnosis` — both used to hold the same message; the
    /// single `engine.diagnosis` now backs them (connection view reads either).
    var backendError: String? { engine.diagnosis }
    var documentCount: Int = 0  // Note: Now tracks active libraries count in multi-library architecture
    var backendVersion: String?
    private(set) var backendAccessError: AccessError?
    /// True while starting/probing. Backed by `engine.phase == .starting`.
    var isCheckingBackend: Bool { engine.isChecking }
    /// Count of consecutive heartbeat failures since the last successful
    /// ping. Used to avoid UI thrash on transient blips — the offline
    /// banner flips only after the count crosses `offlineFlipThreshold`.
    private var heartbeatFailureCount: Int = 0
    private let offlineFlipThreshold: Int = 2
    // Plumbing, not observed UI state — exclude from @Observable tracking, and
    // `nonisolated(unsafe)` so `deinit` (nonisolated in Swift 6) can cancel it
    // (only mutated on the main actor; `Task.cancel()` is safe from anywhere).
    @ObservationIgnored nonisolated(unsafe) private var heartbeatTask: Task<Void, Never>?

    // MARK: - Provider Management

    var providers: [Components.Schemas.ProviderResponse] = []
    var showAddProvider: Bool = false
    var hasCheckedProviders: Bool = false
    var isFirstLaunchProviderSetup: Bool = false  // True when showing Add Provider on first launch

    // MARK: - MCP Server Management

    var selectedSettingsTab: SettingsTab = .aiModels

    /// A `fichero://pair` link the user opened, waiting for them to confirm (#3788).
    ///
    /// A tapped link must NEVER pair silently: it repoints this Mac at a remote host,
    /// which is a trust decision. So the link only PREFILLS the existing Mac pairing
    /// field, and the user still presses Connect — the same confirm-before-pair shape
    /// iOS has. Cleared once consumed.
    var pendingPairingInvite: String?

    var showMCPServers: Bool = false {
        didSet {
            guard showMCPServers else { return }
            openSettings(tab: .mcp)
            showMCPServers = false
        }
    }

    // MARK: - Integrations (Hazel-like folder/app observers)

    var showFolderWatchers: Bool = false {
        didSet {
            guard showFolderWatchers else { return }
            openSettings(tab: .integrations)
            showFolderWatchers = false
        }
    }
    var showAppObservers: Bool = false {
        didSet {
            guard showAppObservers else { return }
            openSettings(tab: .integrations)
            showAppObservers = false
        }
    }
    var showAutomationRules: Bool = false {
        didSet {
            guard showAutomationRules else { return }
            openSettings(tab: .integrations)
            showAutomationRules = false
        }
    }

    // MARK: - Services

    private let apiClient = APIClient()  // App-wide APIClient for legacy services
    private let ficheroClient = FicheroClient(baseURL: EngineConfig.host)  // App-wide generated client
    let providerService: ProviderAPIService  // Public for @EnvironmentObject injection
    let mcpService: MCPService  // Public for @EnvironmentObject injection
    let modelService: ModelService  // Public for @EnvironmentObject injection (HuggingFace browsing)
    let usersStore: UsersStore  // Public for Settings → Users tab
    let sessionStore: SessionStore  // Public for the login gate (#2021/#2022)
    let identityStore: IdentityStore  // Public for the access UX (F5): who am I / owner?
    let localInferenceStore: LocalInferenceStore  // Public for Settings → Local LLM tab (#3120)
    let appleAvailabilityStore: AppleAvailabilityStore  // Public for FirstRun + provider rows (#3121/#3118)
    let kgQueryStore: KGQueryStore  // Public for the SPARQL console (#3298); the store is the only endpoint accessor (#1863)
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "AppState")

    // MARK: - Initialization

    init() {
        // Opens the whole-launch signpost interval; ContentView's first frame
        // closes it. The milestone's elapsed value IS the pre-main cost (dyld +
        // static init), which nothing measured before (#3946).
        LaunchProfile.beginLaunch()
        LaunchProfile.milestone("AppState.init entry")
        // Initialize services with app-wide clients
        self.providerService = ProviderAPIService(ficheroClient: ficheroClient)
        self.mcpService = MCPService(apiClient: apiClient)
        self.modelService = ModelService(ficheroClient: ficheroClient)
        self.usersStore = UsersStore(client: ficheroClient)
        self.sessionStore = SessionStore(client: ficheroClient)
        self.identityStore = IdentityStore(client: ficheroClient)
        self.localInferenceStore = LocalInferenceStore(client: ficheroClient)
        self.appleAvailabilityStore = AppleAvailabilityStore(client: ficheroClient)
        self.kgQueryStore = KGQueryStore(client: ficheroClient)
        LaunchProfile.milestone("AppState.init services ready")
        // #2960: engine is `@Observable`; the computed backend shims read
        // `engine.phase` directly, so views observing them track the engine
        // transitively. The former `objectWillChange` re-publish is retired.
    }

    deinit {
        heartbeatTask?.cancel()
    }

    func openSettings(tab: SettingsTab) {
        selectedSettingsTab = resolvedSettingsTab(for: tab)
        #if canImport(AppKit)
        NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
        #endif
    }

    private func resolvedSettingsTab(for requestedTab: SettingsTab) -> SettingsTab {
        let featureManager = FeatureManager.shared
        switch requestedTab {
        case .mcp where !featureManager.isMCPEnabled:
            return .aiModels
        case .integrations where !featureManager.isIntegrationsEnabled:
            return .aiModels
        default:
            return requestedTab
        }
    }

    // MARK: - Heartbeat

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
        switch await EngineReadinessProbe(hostURL: EngineConfig.host).probe() {
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
    private func confirmAuthAndLoad(readinessAlreadyProven: Bool = false) async {
        if readinessAlreadyProven {
            await warmContextThenMarkReady()
            return
        }
        switch await EngineReadinessProbe(hostURL: EngineConfig.host).probe() {
        case .ready:
            await warmContextThenMarkReady()
        case .authRejected:
            let accessError = await EngineReadinessProbe(hostURL: EngineConfig.host).authFailure() ?? .unauthenticated
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
    private func warmContextThenMarkReady() async {
        async let session: Void = sessionStore.refresh()
        async let identity: Void = identityStore.load()
        _ = await (session, identity)
        recordActiveEndpoint()
        backendAccessError = nil
        engine.markReady()
        await loadProviders()
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
            switch await EngineReadinessProbe(hostURL: candidate.url).probe() {
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

    /// Remember the endpoint the app is currently connected to so failover can
    /// walk back to it later (#3098). No-op for the local engine — loopback is
    /// never a failover target.
    private func recordActiveEndpoint() {
        PairedHostEndpointStore.record(EngineConfig.host)
    }

    // MARK: - Backend Health

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
        // ready / unreachable / authRejected (via confirmAuthAndLoad).
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
                logger.info("Backend connected: v\(health.backendVersion ?? "unknown"), \(health.activeLibraries ?? 0) active libraries")
                // Health 200 is necessary but NOT sufficient (#2864): confirm the
                // engine accepts our token, then — on the ready path —
                // resolve the login gate (#2021/#2022) and identity (F5) BEFORE
                // flipping ready, so the first library fetch is authorized (#2407).
                // `confirmAuthAndLoad` owns that full ordering; the login gate and
                // identity are no longer raced after `markReady`.
                await confirmAuthAndLoad()

            default:
                backendAccessError = nil
                engine.markUnreachable("API returned error status")
            }

        } catch let error as URLError where error.code == .cannotConnectToHost {
            backendAccessError = .engineUnreachable
            engine.markUnreachable("""
                Cannot connect to API server.

                Please start the API first:

                PYTHONPATH=src python -m fichero.api
                """)
            logger.error("Backend not reachable: \(error.localizedDescription)")
        } catch {
            let accessError = AccessError.classify(error)
            backendAccessError = accessError
            engine.markUnreachable(Self.diagnosis(for: accessError))
            logger.error("Backend health check failed: \(error.localizedDescription)")
        }
    }

    nonisolated static func diagnosis(for error: AccessError) -> String {
        switch error {
        case .staleBootstrapToken:
            return "Fichero connected to the engine, but this app's saved engine token is out of date. Restart the engine and try again."
        case .unauthenticated:
            return "Fichero connected to the engine, but the saved sign-in is out of date. Reset Sign-In & Retry."
        case .tlsPinFailure:
            return "This app's pinned certificate doesn't match the running engine. Reset the certificate and retry."
        case .deviceAccessExpired:
            return "This device's access has expired. Re-pair it with the engine and try again."
        case .engineUnreachable:
            return "The Fichero engine isn't reachable. Start or restart it, then try again."
        case .forbidden(_, let message):
            return message ?? "This app doesn't have access to the running engine."
        case .transport(let description):
            return "Failed to connect to the engine: \(description)"
        }
    }

    func loadProviders() async {
        guard FeatureManager.shared.isVisible(.providers) else {
            providers = []
            hasCheckedProviders = true
            return
        }
        do {
            providers = try await providerService.listProviders()

            // On first check, if no providers configured, remember it's a
            // first-launch setup — but do NOT auto-present the sheet here.
            // loadProviders() runs during launch; presenting a sheet while the
            // main window's NSToolbar is still doing its first layout re-enters
            // the toolbar update and double-inserts an item, crashing at launch
            // on macOS 27 (#3163). Users add a provider from Settings ▸ Providers.
            if !hasCheckedProviders && providers.isEmpty {
                isFirstLaunchProviderSetup = true
            }

            hasCheckedProviders = true
        } catch {
            logger.error("Failed to load providers: \(error.localizedDescription)")
            hasCheckedProviders = true
        }
    }

    /// Show Add Provider from menu (not first launch)
    func showAddProviderFromMenu() {
        isFirstLaunchProviderSetup = false
        showAddProvider = true
    }

    // MARK: - AI Defaults

    func fetchAIDefaults() async throws -> AIDefaults {
        let response = try await ficheroClient.api.getAiDefaultsApiSettingsAiDefaultsGet(headers: .init())
        switch response {
        case .ok(let okResponse):
            let generated = try okResponse.body.json
            return AppState.map(generated)
        default:
            throw APIError.invalidResponse
        }
    }

    func saveAIDefaults(_ defaults: AIDefaults) async throws {
        let update = AppState.mapToUpdate(defaults)
        let response = try await ficheroClient.api.setAiDefaultsApiSettingsAiDefaultsPut(body: .json(update))
        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw APIError.httpError(statusCode: 422, message: detail?.detail?.description ?? "Validation error")
        default:
            throw APIError.invalidResponse
        }
    }

    func resetAIDefaults() async throws {
        let response = try await ficheroClient.api.resetAiDefaultsApiSettingsAiDefaultsDelete(headers: .init())
        switch response {
        case .ok:
            return
        default:
            throw APIError.invalidResponse
        }
    }
}

// MARK: - AI Defaults Mapping

extension AppState {
    /// Map generated OpenAPI AI defaults to the local view model.
    static func map(_ generated: Components.Schemas.AIDefaults) -> AIDefaults {
        AIDefaults(
            visionProvider: generated.visionProvider ?? "",
            visionModel: generated.visionModel ?? "",
            textProvider: generated.textProvider ?? "",
            textModel: generated.textModel ?? "",
            audioProvider: generated.audioProvider ?? "",
            audioModel: generated.audioModel ?? "",
            videoProvider: generated.videoProvider ?? "",
            videoModel: generated.videoModel ?? "",
            embeddingsProvider: generated.embeddingsProvider ?? "",
            embeddingsModel: generated.embeddingsModel ?? "",
            smallProvider: generated.smallProvider ?? "",
            smallModel: generated.smallModel ?? "",
            mediumProvider: generated.mediumProvider ?? "",
            mediumModel: generated.mediumModel ?? "",
            largeProvider: generated.largeProvider ?? "",
            largeModel: generated.largeModel ?? "",
            visionSmallProvider: generated.visionSmallProvider ?? "",
            visionSmallModel: generated.visionSmallModel ?? "",
            visionMediumProvider: generated.visionMediumProvider ?? "",
            visionMediumModel: generated.visionMediumModel ?? "",
            visionLargeProvider: generated.visionLargeProvider ?? "",
            visionLargeModel: generated.visionLargeModel ?? "",
            temperature: generated.temperature ?? "",
            maxTokens: generated.maxTokens ?? "",
            promptPrefix: generated.promptPrefix ?? "",
            primaryLanguage: generated.primaryLanguage ?? ""
        )
    }

    /// Map the local AI defaults view model to the generated update payload.
    static func mapToUpdate(_ defaults: AIDefaults) -> Components.Schemas.AIDefaultsUpdate {
        Components.Schemas.AIDefaultsUpdate(
            visionProvider: defaults.visionProvider,
            visionModel: defaults.visionModel,
            textProvider: defaults.textProvider,
            textModel: defaults.textModel,
            audioProvider: defaults.audioProvider,
            audioModel: defaults.audioModel,
            videoProvider: defaults.videoProvider,
            videoModel: defaults.videoModel,
            embeddingsProvider: defaults.embeddingsProvider,
            embeddingsModel: defaults.embeddingsModel,
            smallProvider: defaults.smallProvider,
            smallModel: defaults.smallModel,
            mediumProvider: defaults.mediumProvider,
            mediumModel: defaults.mediumModel,
            largeProvider: defaults.largeProvider,
            largeModel: defaults.largeModel,
            visionSmallProvider: defaults.visionSmallProvider,
            visionSmallModel: defaults.visionSmallModel,
            visionMediumProvider: defaults.visionMediumProvider,
            visionMediumModel: defaults.visionMediumModel,
            visionLargeProvider: defaults.visionLargeProvider,
            visionLargeModel: defaults.visionLargeModel,
            primaryLanguage: defaults.primaryLanguage,
            temperature: defaults.temperature,
            maxTokens: defaults.maxTokens,
            promptPrefix: defaults.promptPrefix
        )
    }
}
// swiftlint:enable file_length type_body_length
