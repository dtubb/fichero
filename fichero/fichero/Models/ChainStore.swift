import Observation

@MainActor
@Observable
final class ChainStore {
    private let chainService: ChainService

    private(set) var chains: [WorkflowChain] = []
    private(set) var isLoading = false
    private(set) var error: String?

    init(chainService: ChainService) {
        self.chainService = chainService
        syncFromService()
    }

    func loadChains() async {
        isLoading = true
        await chainService.loadChains()
        syncFromService()
        isLoading = false
    }

    @discardableResult
    func createChain(
        name: String,
        description: String = "",
        steps: [ChainStep] = [],
        entryStep: String? = nil,
        initialInputs: [String: AnyCodableValue] = [:]
    ) async throws -> WorkflowChain {
        let chain = try await chainService.createChain(
            name: name,
            description: description,
            steps: steps,
            entryStep: entryStep,
            initialInputs: initialInputs
        )
        syncFromService()
        return chain
    }

    func deleteChain(_ id: String) async throws {
        try await chainService.deleteChain(id)
        syncFromService()
    }

    func executeChain(
        chainId: String,
        inputs: [String: AnyCodableValue] = [:],
        inputFiles: [String] = []
    ) async throws -> ExecuteChainResponse {
        try await chainService.executeChain(
            chainId: chainId,
            inputs: inputs,
            inputFiles: inputFiles
        )
    }

    func waitForExecution(
        _ executionId: String,
        onProgress: ((ChainExecutionStatusResponse) -> Void)? = nil
    ) async throws -> ChainExecutionStatusResponse {
        try await chainService.waitForExecution(executionId, onProgress: onProgress)
    }

    private func syncFromService() {
        chains = chainService.chains
        error = chainService.error
    }
}
