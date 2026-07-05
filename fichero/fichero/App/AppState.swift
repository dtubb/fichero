import FicheroAPIClient
import Foundation
import Observation
import OSLog
import SwiftUI

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
    var indexedCount: Int = 0
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

    var showMCPServers: Bool = false

    // MARK: - Integrations (Hazel-like folder/app observers)

    var showFolderWatchers: Bool = false
    var showAppObservers: Bool = false
    var showAutomationRules: Bool = false

    // MARK: - Services

    private let apiClient = APIClient()  // App-wide APIClient for legacy services
    private let ficheroClient = FicheroClient(baseURL: EngineConfig.host)  // App-wide generated client
    let providerService: ProviderServiceGenerated  // Public for @EnvironmentObject injection
    let mcpService: MCPService  // Public for @EnvironmentObject injection
    let modelService: ModelServiceGenerated  // Public for @EnvironmentObject injection (HuggingFace browsing)
    let usersStore: UsersStore  // Public for Settings → Users tab
    let sessionStore: SessionStore  // Public for the login gate (#2021/#2022)
    let identityStore: IdentityStore  // Public for the access UX (F5): who am I / owner?
    let localInferenceStore: LocalInferenceStore  // Public for Settings → Local LLM tab (#3120)
    let appleAvailabilityStore: AppleAvailabilityStore  // Public for FirstRun + provider rows (#3121/#3118)
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "AppState")

    // MARK: - Initialization

    init() {
        logger.info("⏱ AppState.init entry")
        // Initialize services with app-wide clients
        self.providerService = ProviderServiceGenerated(ficheroClient: ficheroClient)
        self.mcpService = MCPService(apiClient: apiClient)
        self.modelService = ModelServiceGenerated(ficheroClient: ficheroClient)
        self.usersStore = UsersStore(client: ficheroClient)
        self.sessionStore = SessionStore(client: ficheroClient)
        self.identityStore = IdentityStore(client: ficheroClient)
        self.localInferenceStore = LocalInferenceStore(client: ficheroClient)
        self.appleAvailabilityStore = AppleAvailabilityStore(client: ficheroClient)
        logger.info("⏱ AppState.init services ready")
        // #2960: engine is `@Observable`; the computed backend shims read
        // `engine.phase` directly, so views observing them track the engine
        // transitively. The former `objectWillChange` re-publish is retired.
    }

    deinit {
        heartbeatTask?.cancel()
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
        NotificationCenter.default.post(name: EngineConfig.engineHostDidChangeNotification, object: nil)
    }

    private func pingBackendOnce() async {
        // Health-200 alone is NOT "online" (#2864): a leftover engine can answer
        // health yet reject our token. The shared readiness probe (#3106) does
        // health + authenticated registry in one, over the pinned transport.
        switch await EngineReadinessProbe(hostURL: EngineConfig.host).probe() {
        case .ready:
            heartbeatFailureCount = 0
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
            noteHeartbeatFailure(reason: "engine not responding")
        case .identityMismatch:
            noteHeartbeatFailure(reason: "engine identity mismatch")
        }
    }

    /// After a health-200, confirm the engine accepts our token, resolve the full
    /// auth context (token + session + identity), and only THEN flip ready and load
    /// providers — or flip authBroken/unreachable with a diagnosis (#2864). Uses
    /// the one shared readiness probe (#3106). Owning the whole ordering here is
    /// what keeps the first library fetch authorized (#2407): nothing that a
    /// library-scoped request depends on is resolved after `markReady`.
    private func confirmAuthAndLoad() async {
        switch await EngineReadinessProbe(hostURL: EngineConfig.host).probe() {
        case .ready:
            // #2407: warm the ENTIRE auth context BEFORE flipping ready. The
            // instant `isBackendRunning` becomes true, `DocumentTabView` mounts the
            // library content and every sub-view `.task` fires a library-scoped
            // fetch (chains/documents/workflows/conversations/saved-search). If the
            // bearer token, restored session, and resolved identity aren't ALL in
            // place first, that first burst races the warm-up and 403s (then 200s
            // on retry). So resolve them here and make `markReady()` the LAST step —
            // the readiness gate the first data call awaits, not a blind retry.
            _ = await AuthTokenMiddleware.waitForToken()
            await sessionStore.refresh()
            await identityStore.load()
            engine.markReady()
            await loadProviders()
        case .authRejected:
            engine.markAuthRejected(
                "The engine is running but rejected this app's credentials. "
                + "The token the app holds doesn't match the engine's."
            )
            logger.error("Auth rejected on readiness probe — authBroken")
        case .notResponding, .identityMismatch:
            engine.markUnreachable(
                "The engine answered health checks but the authenticated readiness probe failed."
            )
        }
    }

    private func noteHeartbeatFailure(reason: String) {
        heartbeatFailureCount += 1
        guard heartbeatFailureCount >= offlineFlipThreshold else { return }
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

    // MARK: - Backend Health

    /// Check if the Python API is running
    func checkBackendHealth() async {
        reconfigureGeneratedClientsForCurrentHost()
        logger.info("⏱ checkBackendHealth entry")
        // Enter the checking/starting phase; the outcome below resolves it to
        // ready / unreachable / authRejected (via confirmAuthAndLoad).
        engine.markStarting()

        logger.info("⏱ checkBackendHealth request-start")
        do {
            let response = try await ficheroClient.api.healthCheckApiHealthGet(headers: .init())
            switch response {
            case .ok(let okResponse):
                let health = try okResponse.body.json
                documentCount = health.activeLibraries ?? 0
                logger.info("Backend connected: v\(health.backendVersion ?? "unknown"), \(health.activeLibraries ?? 0) active libraries")
                // Health 200 is necessary but NOT sufficient (#2864): confirm the
                // engine accepts our token, then — on the ready path —
                // resolve the login gate (#2021/#2022) and identity (F5) BEFORE
                // flipping ready, so the first library fetch is authorized (#2407).
                // `confirmAuthAndLoad` owns that full ordering; the login gate and
                // identity are no longer raced after `markReady`.
                await confirmAuthAndLoad()

            default:
                engine.markUnreachable("API returned error status")
            }

        } catch let error as URLError where error.code == .cannotConnectToHost {
            engine.markUnreachable("""
                Cannot connect to API server.

                Please start the API first:

                PYTHONPATH=src python -m fichero.api
                """)
            logger.error("Backend not reachable: \(error.localizedDescription)")
        } catch {
            engine.markUnreachable("Failed to connect to API: \(error.localizedDescription)")
            logger.error("Backend health check failed: \(error.localizedDescription)")
        }
    }

    func loadProviders() async {
        do {
            providers = try await providerService.listProviders()

            // On first check, if no providers configured, show Add Provider as first launch
            if !hasCheckedProviders && providers.isEmpty {
                isFirstLaunchProviderSetup = true
                showAddProvider = true
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
            largeProvider: generated.largeProvider ?? "",
            largeModel: generated.largeModel ?? "",
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
            largeProvider: defaults.largeProvider,
            largeModel: defaults.largeModel,
            primaryLanguage: defaults.primaryLanguage,
            temperature: defaults.temperature,
            maxTokens: defaults.maxTokens,
            promptPrefix: defaults.promptPrefix
        )
    }
}
