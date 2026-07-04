import FicheroAPIClient
import Foundation
import OSLog
import SwiftUI

/// Global app state including backend connection and provider management
@MainActor
class AppState: ObservableObject {
    // MARK: - Backend State

    @Published var isBackendRunning: Bool = false
    /// True when the engine answers health checks but REJECTS the app's token
    /// (HTTP 401/403). Health-200-but-auth-broken is exactly the state that
    /// used to render content and then 401 every call into a blank window
    /// (#2864). The window root shows a full-window error for this state.
    @Published var authBroken: Bool = false
    /// Human-readable cause for the current unreachable/authBroken/failed
    /// state (port occupied by PID / auth rejected / probe failed), shown in
    /// the full-window error.
    @Published var backendDiagnosis: String?
    @Published var backendError: String?
    @Published var documentCount: Int = 0  // Note: Now tracks active libraries count in multi-library architecture
    @Published var indexedCount: Int = 0
    @Published var isCheckingBackend: Bool = true  // True while checking API
    /// Count of consecutive heartbeat failures since the last successful
    /// ping. Used to avoid UI thrash on transient blips — the offline
    /// banner flips only after the count crosses `offlineFlipThreshold`.
    private var heartbeatFailureCount: Int = 0
    private let offlineFlipThreshold: Int = 2
    private var heartbeatTask: Task<Void, Never>?

    // MARK: - Provider Management

    @Published var providers: [Components.Schemas.ProviderResponse] = []
    @Published var showAddProvider: Bool = false
    @Published var hasCheckedProviders: Bool = false
    @Published var isFirstLaunchProviderSetup: Bool = false  // True when showing Add Provider on first launch

    // MARK: - MCP Server Management

    @Published var showMCPServers: Bool = false

    // MARK: - Integrations (Hazel-like folder/app observers)

    @Published var showFolderWatchers: Bool = false
    @Published var showAppObservers: Bool = false
    @Published var showAutomationRules: Bool = false

    // MARK: - Services

    private let apiClient = APIClient()  // App-wide APIClient for legacy services
    private let ficheroClient = FicheroClient(baseURL: EngineConfig.host)  // App-wide generated client
    let providerService: ProviderServiceGenerated  // Public for @EnvironmentObject injection
    let mcpService: MCPService  // Public for @EnvironmentObject injection
    let modelService: ModelServiceGenerated  // Public for @EnvironmentObject injection (HuggingFace browsing)
    let usersStore: UsersStore  // Public for Settings → Users tab
    let sessionStore: SessionStore  // Public for the login gate (#2021/#2022)
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
        logger.info("⏱ AppState.init services ready")
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
        do {
            let response = try await ficheroClient.api.healthCheckApiHealthGet(headers: .init())
            switch response {
            case .ok:
                // Health-200 alone is NOT "online" (#2864): a leftover engine
                // can answer health yet reject our token. Confirm auth before
                // declaring recovery, and flip authBroken if it rejects us so
                // the full-window error shows instead of silent 401s.
                let status = await probeAuthenticatedRegistry()
                switch status {
                case 200:
                    heartbeatFailureCount = 0
                    authBroken = false
                    if !isBackendRunning {
                        isBackendRunning = true
                        backendError = nil
                        backendDiagnosis = nil
                        logger.info("Backend heartbeat: recovered — back online")
                        // Reload providers now that the engine is back so list
                        // views aren't empty until next manual refresh.
                        await loadProviders()
                    }
                case 401, 403:
                    heartbeatFailureCount = 0
                    authBroken = true
                    isBackendRunning = false
                    backendDiagnosis =
                        "The engine is running but rejected this app's credentials (HTTP \(status ?? 401))."
                    backendError = backendDiagnosis
                    logger.warning("Backend heartbeat: auth rejected — flipping authBroken")
                default:
                    noteHeartbeatFailure(reason: "authenticated probe failed")
                }
            default:
                noteHeartbeatFailure(reason: "API returned error status")
            }
        } catch {
            noteHeartbeatFailure(reason: error.localizedDescription)
        }
    }

    /// After a health-200, confirm the engine accepts our token and load
    /// providers, or flip authBroken/unreachable with a diagnosis (#2864).
    private func confirmAuthAndLoad() async {
        let status = await probeAuthenticatedRegistry()
        switch status {
        case 200:
            isBackendRunning = true
            authBroken = false
            backendError = nil
            backendDiagnosis = nil
            _ = await AuthTokenMiddleware.waitForToken()
            await loadProviders()
        case 401, 403:
            isBackendRunning = false
            authBroken = true
            backendDiagnosis =
                "The engine is running but rejected this app's credentials (HTTP \(status ?? 401)). "
                + "The token the app holds doesn't match the engine's."
            backendError = backendDiagnosis
            logger.error("Auth rejected on readiness probe — authBroken")
        default:
            isBackendRunning = false
            authBroken = false
            backendDiagnosis =
                "The engine answered health checks but the authenticated probe failed"
                + (status.map { " (HTTP \($0))" } ?? " (no response)") + "."
            backendError = backendDiagnosis
        }
    }

    /// GET /api/registry with the app's token — authenticated but needs no
    /// library header, so it cleanly exercises auth. Returns the HTTP status
    /// (200 ok, 401/403 auth rejected) or nil on a transport error. Shares the
    /// engine's readiness contract with EmbeddedBackendService.probeReadiness.
    private func probeAuthenticatedRegistry() async -> Int? {
        let url = EngineConfig.apiBaseURL.appendingPathComponent("registry")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.addEngineAuth()
        let session = RemoteCertificatePinning.configuredSession()
        do {
            let (_, response) = try await session.data(for: request)
            return (response as? HTTPURLResponse)?.statusCode
        } catch {
            return nil
        }
    }

    private func noteHeartbeatFailure(reason: String) {
        heartbeatFailureCount += 1
        guard heartbeatFailureCount >= offlineFlipThreshold else { return }
        if isBackendRunning {
            logger.warning(
                "Backend heartbeat: \(self.heartbeatFailureCount) consecutive failures — flipping offline (\(reason))"
            )
            isBackendRunning = false
            backendError = """
                Lost connection to the Fichero engine.

                The backend stopped responding mid-session. Restart it with:

                PYTHONPATH=src python -m fichero.api
                """
        }
    }

    // MARK: - Backend Health

    /// Check if the Python API is running
    func checkBackendHealth() async {
        reconfigureGeneratedClientsForCurrentHost()
        logger.info("⏱ checkBackendHealth entry")
        isCheckingBackend = true
        defer { isCheckingBackend = false }

        logger.info("⏱ checkBackendHealth request-start")
        do {
            let response = try await ficheroClient.api.healthCheckApiHealthGet(headers: .init())
            switch response {
            case .ok(let okResponse):
                let health = try okResponse.body.json
                documentCount = health.activeLibraries ?? 0
                logger.info("Backend connected: v\(health.backendVersion ?? "unknown"), \(health.activeLibraries ?? 0) active libraries")
                // Health 200 is necessary but NOT sufficient (#2864): confirm
                // the engine accepts our token before declaring it usable.
                await confirmAuthAndLoad()

                // Resolve the multi-user login gate (#2021/#2022): restores a
                // stored session, or flips ContentView to the login / owner-setup
                // screen. A no-op (phase → .disabled) when multi-user is off.
                await sessionStore.refresh()

            default:
                backendError = "API returned error status"
                backendDiagnosis = backendError
                isBackendRunning = false
            }

        } catch let error as URLError where error.code == .cannotConnectToHost {
            backendError = """
                Cannot connect to API server.

                Please start the API first:

                PYTHONPATH=src python -m fichero.api
                """
            isBackendRunning = false
            logger.error("Backend not reachable: \(error.localizedDescription)")
        } catch {
            backendError = "Failed to connect to API: \(error.localizedDescription)"
            isBackendRunning = false
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
            temperature: defaults.temperature,
            maxTokens: defaults.maxTokens,
            promptPrefix: defaults.promptPrefix,
            primaryLanguage: defaults.primaryLanguage
        )
    }
}
