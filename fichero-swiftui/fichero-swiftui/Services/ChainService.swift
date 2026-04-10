import Combine
import Foundation
import OSLog

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "ChainService")

/// Service for managing workflow chains via the backend API.
/// Observers should use Combine to subscribe to $chains instead of NotificationCenter.
@MainActor
class ChainService: ObservableObject {
    private let api: APIClient

    @Published var chains: [WorkflowChain] = []
    @Published var isLoading = false
    @Published var error: String?

    init(apiClient: APIClient) {
        self.api = apiClient
    }

    // MARK: - Chain CRUD

    /// List all workflow chains.
    func listChains(limit: Int = 50) async throws -> [WorkflowChain] {
        let response: ChainListResponse = try await api.get("/chains", query: ["limit": String(limit)])
        return response.chains
    }

    /// Load chains into published property.
    func loadChains() async {
        isLoading = true
        error = nil

        do {
            chains = try await listChains()
            logger.info("Loaded \(self.chains.count) chains")
        } catch {
            self.error = error.localizedDescription
            logger.error("Failed to load chains: \(error.localizedDescription)")
        }

        isLoading = false
    }

    /// Get a specific chain by ID.
    func getChain(_ id: String) async throws -> WorkflowChain {
        try await api.get("/chains/\(id)")
    }

    /// Create a new workflow chain.
    func createChain(
        name: String,
        description: String = "",
        steps: [ChainStep] = [],
        entryStep: String? = nil,
        initialInputs: [String: AnyCodableValue] = [:]
    ) async throws -> WorkflowChain {
        let request = CreateChainRequest(
            name: name,
            description: description,
            steps: steps,
            entryStep: entryStep,
            initialInputs: initialInputs
        )
        let chain: WorkflowChain = try await api.post("/chains", body: request)
        logger.info("Created chain: \(chain.name)")

        // Refresh list - observers subscribe to $chains via Combine
        await loadChains()

        return chain
    }

    /// Update an existing chain.
    func updateChain(_ chain: WorkflowChain) async throws -> WorkflowChain {
        let updated: WorkflowChain = try await api.put("/chains/\(chain.id)", body: chain)
        logger.info("Updated chain: \(updated.name)")

        // Refresh list
        await loadChains()

        return updated
    }

    /// Delete a chain by ID.
    func deleteChain(_ id: String) async throws {
        try await api.delete("/chains/\(id)")
        logger.info("Deleted chain: \(id)")

        // Remove from local list
        chains.removeAll { $0.id == id }
    }

    // MARK: - Chain Execution

    /// Execute a workflow chain.
    func executeChain(
        chainId: String,
        inputs: [String: AnyCodableValue] = [:],
        inputFiles: [String] = []
    ) async throws -> ExecuteChainResponse {
        let request = ExecuteChainRequest(inputs: inputs, inputFiles: inputFiles)
        let response: ExecuteChainResponse = try await api.post("/chains/\(chainId)/execute", body: request)
        logger.info("Started chain execution: \(response.executionId)")
        return response
    }

    /// Get status of a chain execution.
    func getExecutionStatus(_ executionId: String) async throws -> ChainExecutionStatusResponse {
        try await api.get("/chains/executions/\(executionId)")
    }

    /// Poll execution status until complete.
    func waitForExecution(
        _ executionId: String,
        pollInterval: TimeInterval = 1.0,
        timeout: TimeInterval = 600.0,
        onProgress: ((ChainExecutionStatusResponse) -> Void)? = nil
    ) async throws -> ChainExecutionStatusResponse {
        let startTime = Date()

        while true {
            let status = try await getExecutionStatus(executionId)
            onProgress?(status)

            // Check if complete
            if status.status == "completed" || status.status == "failed" || status.status == "cancelled" {
                return status
            }

            // Check timeout
            if Date().timeIntervalSince(startTime) > timeout {
                throw ChainServiceError.timeout
            }

            // Wait before next poll
            try await Task.sleep(nanoseconds: UInt64(pollInterval * 1_000_000_000))
        }
    }
}

// MARK: - Errors

enum ChainServiceError: LocalizedError {
    case timeout
    case notFound(String)

    var errorDescription: String? {
        switch self {
        case .timeout:
            return "Chain execution timed out"
        case .notFound(let id):
            return "Chain not found: \(id)"
        }
    }
}
