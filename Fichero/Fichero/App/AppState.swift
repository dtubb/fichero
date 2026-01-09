import SwiftUI
import Foundation
import OSLog

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

    @Published var providers: [ProviderResponse] = []
    @Published var showProvidersSettings: Bool = false
    @Published var showAddProvider: Bool = false
    @Published var hasCheckedProviders: Bool = false
    @Published var isFirstLaunchProviderSetup: Bool = false  // True when showing Add Provider on first launch

    // MARK: - MCP Server Management

    @Published var showMCPServers: Bool = false

    // MARK: - Services

    private let apiClient = APIClient()  // App-wide APIClient for global services
    private let providerService: ProviderService
    let mcpService: MCPService  // Public for @EnvironmentObject injection
    private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "AppState")

    // MARK: - Initialization

    init() {
        // Initialize services with app-wide APIClient
        self.providerService = ProviderService(apiClient: apiClient)
        self.mcpService = MCPService(apiClient: apiClient)

        // Check API health on launch
        Task {
            await checkBackendHealth()
        }
    }

    // MARK: - Backend Health

    /// Check if the Python API is running
    func checkBackendHealth() async {
        isCheckingBackend = true
        defer { isCheckingBackend = false }

        guard let url = URL(string: "http://127.0.0.1:8765/api/health") else {
            backendError = "Invalid API URL"
            isBackendRunning = false
            return
        }

        do {
            let (data, response) = try await URLSession.shared.data(from: url)

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

    // MARK: - Future Features

    func refreshStats() async {
        // TODO: Implement stats refresh via GET /api/stats
        logger.warning("refreshStats not yet implemented")
    }

    func startBackend() async {
        // TODO: Launch Python backend subprocess: python -m fichero serve
        logger.warning("startBackend not yet implemented")
    }

    func stopBackend() {
        // TODO: Terminate backend subprocess
        logger.warning("stopBackend not yet implemented")
    }
}
