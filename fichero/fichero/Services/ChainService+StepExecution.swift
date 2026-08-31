import FicheroAPIClient
import Foundation
import OSLog

private let logger = Logger(
    subsystem: "app.fichero.fichero", category: "ChainService"
)

// Step-wise chain execution (workflow bar, 2026-08-30). In its own file so
// ChainService.swift stays inside the file-length budget.
extension ChainService {

    /// Run a chain's steps as real, sequential workflow runs (workflow bar,
    /// 2026-08-30): the engine owns order, per-step model overrides and
    /// stop-on-failure; each step gets a pre-assigned thread id so its run
    /// can be watched from the first moment.
    ///
    /// Throws `.stepExecutionUnavailable` on a 404 so the caller can
    /// feature-detect: an older engine has no execute-steps route, and the
    /// bar falls back to its client-side loop rather than breaking.
    func executeChainSteps(
        chainId: String,
        inputs: [String: AnyCodableValue] = [:]
    ) async throws -> ChainStepsExecution {
        struct WireRequest: Encodable {
            let inputs: [String: AnyCodableValue]
        }
        let body: Components.Schemas.ExecuteChainStepsRequest =
            try encodeChainBody(WireRequest(inputs: inputs))
        let response = try await apiClient.api.executeChainStepsApiChainsChainIdExecuteStepsPost(
            .init(path: .init(chainId: chainId), body: .json(body))
        )
        switch response {
        case .accepted(let accepted):
            // Same wire-faithful round-trip as the chain mappers below: the
            // generated schema and the app model share the snake_case shape.
            let data = try JSONEncoder().encode(try accepted.body.json)
            let execution = try JSONDecoder().decode(ChainStepsExecution.self, from: data)
            logger.info("Started chain step execution: \(execution.executionId)")
            return execution
        case .unprocessableContent(let error):
            throw ChainServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        case .undocumented(statusCode: 404, _):
            throw ChainServiceError.stepExecutionUnavailable
        default:
            throw ChainServiceError.unexpectedResponse
        }
    }

}
