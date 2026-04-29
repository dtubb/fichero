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

    // MARK: - Provider Management

    @Published var providers: [Components.Schemas.ProviderResponse] = []
    @Published var showProvidersSettings: Bool = false
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

    private let apiClient = APIClient()  // App-wide APIClient for global services
    private let ficheroClient = FicheroClient()  // App-wide FicheroClient for generated services
    let providerService: ProviderServiceGenerated  // Public for @EnvironmentObject injection
    let mcpService: MCPService  // Public for @EnvironmentObject injection
    let modelService: ModelServiceGenerated  // Public for @EnvironmentObject injection (HuggingFace browsing)
    private let logger = Logger(subsystem: "com.fichero.fichero", category: "AppState")

    // MARK: - Initialization

    init() {
        logger.info("⏱ AppState.init entry")
        // Initialize services with app-wide clients
        self.providerService = ProviderServiceGenerated(ficheroClient: ficheroClient)
        self.mcpService = MCPService(apiClient: apiClient)
        self.modelService = ModelServiceGenerated(ficheroClient: ficheroClient)
        logger.info("⏱ AppState.init services ready — queuing health check")

        // Check API health on launch
        Task { @MainActor in
            await checkBackendHealth()
        }
    }

    // MARK: - Backend Health

    /// Check if the Python API is running
    func checkBackendHealth() async {
        logger.info("⏱ checkBackendHealth entry")
        isCheckingBackend = true
        defer { isCheckingBackend = false }

        guard let url = URL(string: "http://127.0.0.1:8765/api/health") else {
            backendError = "Invalid API URL"
            isBackendRunning = false
            return
        }

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
        let url = URL(string: "http://127.0.0.1:8765/api/settings/ai-defaults")!
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (_, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw APIError.invalidResponse
        }
    }

}
