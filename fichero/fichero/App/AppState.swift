import FicheroAPIClient
import Foundation
import OSLog
import SwiftUI

/// Global app state including backend connection and provider management
@MainActor
class AppState: ObservableObject {
    // MARK: - Backend State

    @Published var isBackendRunning: Bool = false
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
    @Published var showProvidersSettings: Bool = false
    @Published var showAddProvider: Bool = false
    @Published var hasCheckedProviders: Bool = false
    @Published var isFirstLaunchProviderSetup: Bool = false  // True when showing Add Provider on first launch

    // MARK: - MCP Server Management

    @Published var showMCPServers: Bool = false

    // MARK: - Notes browser (#1500)

    /// Drives the standalone NotesBrowserView sheet (Data ▸ Notes Browser…).
    @Published var showNotesBrowser: Bool = false

    // MARK: - Integrations (Hazel-like folder/app observers)

    @Published var showFolderWatchers: Bool = false
    @Published var showAppObservers: Bool = false
    @Published var showAutomationRules: Bool = false

    // MARK: - Services

    private let apiClient = APIClient()  // App-wide APIClient for global services
    private let ficheroClient = FicheroClient()  // App-wide FicheroClient for generated services
    let providerService: ProviderServiceGenerated  // Public for @EnvironmentObject injection
    let mcpService: MCPService  // Public for @EnvironmentObject injection
    let modelService: ModelServiceGenerated  // Public for @EnvironmentObject injection (HuggingFace browsing)
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "AppState")

    // MARK: - Initialization

    init() {
        logger.info("⏱ AppState.init entry")
        // Initialize services with app-wide clients
        self.providerService = ProviderServiceGenerated(ficheroClient: ficheroClient)
        self.mcpService = MCPService(apiClient: apiClient)
        self.modelService = ModelServiceGenerated(ficheroClient: ficheroClient)
        logger.info("⏱ AppState.init services ready — queuing health check")

        // Check API health on launch, then start the periodic heartbeat
        // so the offline banner appears if the engine goes down mid-session
        // (#967 — Daniel: "the app kept working, and failed silently").
        Task { @MainActor in
            await checkBackendHealth()
            startBackendHeartbeat()
        }
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

    private func pingBackendOnce() async {
        let url = EngineConfig.apiBaseURL.appendingPathComponent("health")
        var request = URLRequest(url: url)
        request.timeoutInterval = 3
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                noteHeartbeatFailure(reason: "API returned error status")
                return
            }
            // Success — flip back online immediately so the offline banner
            // clears the moment the engine comes back. Reset the failure
            // streak.
            heartbeatFailureCount = 0
            if !isBackendRunning {
                isBackendRunning = true
                backendError = nil
                logger.info("Backend heartbeat: recovered — back online")
                // Reload providers now that the engine is back so list
                // views aren't empty until next manual refresh.
                await loadProviders()
            }
        } catch {
            noteHeartbeatFailure(reason: error.localizedDescription)
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
        logger.info("⏱ checkBackendHealth entry")
        isCheckingBackend = true
        defer { isCheckingBackend = false }

        let url = EngineConfig.apiBaseURL.appendingPathComponent("health")

        logger.info("⏱ checkBackendHealth request-start → \(url.absoluteString)")
        do {
            let (data, response) = try await URLSession.shared.data(from: url)
            logger.info("⏱ checkBackendHealth response-received")

            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else {
                backendError = "API returned error status"
                isBackendRunning = false
                return
            }

            // Parse health response
            struct HealthResponse: Codable {
                let status: String
                let backendVersion: String
                let activeLibraries: Int

                // swiftlint:disable:next nesting
                enum CodingKeys: String, CodingKey {
                    case status
                    case backendVersion = "backend_version"
                    case activeLibraries = "active_libraries"
                }
            }

            let health = try JSONDecoder().decode(HealthResponse.self, from: data)
            documentCount = health.activeLibraries  // Track number of active libraries instead
            isBackendRunning = true
            backendError = nil
            logger.info("Backend connected: v\(health.backendVersion), \(health.activeLibraries) active libraries")

            // Now load providers
            _ = await AuthTokenMiddleware.waitForToken()
            await loadProviders()

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
        let result: AIDefaults = try await apiClient.get("/settings/ai-defaults")
        return result
    }

    func saveAIDefaults(_ defaults: AIDefaults) async throws {
        let _: StatusResponse = try await apiClient.put("/settings/ai-defaults", body: defaults)
    }

    func resetAIDefaults() async throws {
        let url = EngineConfig.apiBaseURL.appendingPathComponent("settings/ai-defaults")
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.addEngineAuth()
        let (_, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw APIError.invalidResponse
        }
    }

}
