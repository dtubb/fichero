import Combine
import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ChainService")

/// Service for managing workflow chains via the backend API.
/// Observers should use Combine to subscribe to $chains instead of NotificationCenter.
///
/// Transport uses the generated, typed FicheroAPIClient operations (#3030); the
/// hand-rolled APIClient generic get/post/put/delete are gone. The app-facing
/// `WorkflowChain` etc. are kept so the ~dozen view/model call sites are
/// untouched — only this service's transport + the inline mappers below change.
@MainActor
@Observable
class ChainService {
    private let apiClient: APIClient

    var chains: [WorkflowChain] = []
    var isLoading = false
    var error: String?

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    // MARK: - Chain CRUD

    /// List all workflow chains.
    func listChains(limit: Int = 50) async throws -> [WorkflowChain] {
        let response = try await apiClient.api.listChainsApiChainsGet(
            .init(query: .init(limit: limit))
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.chains.map { try mapChainResponse($0) }
        case .unprocessableContent(let error):
            // Preserve the engine's 422 validation detail instead of collapsing it
            // into a generic "unexpected response" (matches Automation/MCP services).
            throw ChainServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw ChainServiceError.unexpectedResponse
        }
    }

    /// Load chains into published property.
    func loadChains() async {
        isLoading = true
        error = nil

        do {
            chains = try await listChains()
            logger.info("Loaded \(self.chains.count) chains")
        } catch {
            if !error.isCancellationError {
                self.error = error.localizedDescription
                logger.error("Failed to load chains: \(error.localizedDescription)")
            }
        }

        isLoading = false
    }

    /// Get a specific chain by ID.
    func getChain(_ id: String) async throws -> WorkflowChain {
        let response = try await apiClient.api.getChainApiChainsChainIdGet(
            .init(path: .init(chainId: id))
        )
        switch response {
        case .ok(let okResponse):
            return try mapChainResponse(try okResponse.body.json)
        case .unprocessableContent(let error):
            // Preserve the engine's 422 validation detail instead of collapsing it
            // into a generic "unexpected response" (matches Automation/MCP services).
            throw ChainServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw ChainServiceError.unexpectedResponse
        }
    }

    /// Create a new workflow chain.
    func createChain(
        name: String,
        description: String = "",
        steps: [ChainStep] = [],
        entryStep: String? = nil,
        initialInputs: [String: AnyCodableValue] = [:]
    ) async throws -> WorkflowChain {
        let appRequest = CreateChainRequest(
            name: name,
            description: description,
            steps: steps,
            entryStep: entryStep,
            initialInputs: initialInputs
        )
        let body: Components.Schemas.CreateChainRequest = try encodeChainBody(appRequest)
        let response = try await apiClient.api.createChainApiChainsPost(
            .init(body: .json(body))
        )
        switch response {
        case .ok(let okResponse):
            let chain = try mapChainResponse(try okResponse.body.json)
            logger.info("Created chain: \(chain.name)")
            // Refresh list - observers subscribe to $chains via Combine
            await loadChains()
            return chain
        case .unprocessableContent(let error):
            // Preserve the engine's 422 validation detail instead of collapsing it
            // into a generic "unexpected response" (matches Automation/MCP services).
            throw ChainServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw ChainServiceError.unexpectedResponse
        }
    }

    /// Update an existing chain.
    ///
    /// The generated (and backend) UpdateChainRequest intentionally omits
    /// folder_path/sort_order — those are create-time/server-managed and were
    /// ignored by the legacy PUT too, so this is behavior-preserving.
    func updateChain(_ chain: WorkflowChain) async throws -> WorkflowChain {
        let appRequest = CreateChainRequest(
            name: chain.name,
            description: chain.description,
            steps: chain.steps,
            entryStep: chain.entryStep,
            initialInputs: chain.initialInputs
        )
        let body: Components.Schemas.UpdateChainRequest = try encodeChainBody(appRequest)
        let response = try await apiClient.api.updateChainApiChainsChainIdPut(
            .init(path: .init(chainId: chain.id), body: .json(body))
        )
        switch response {
        case .ok(let okResponse):
            let updated = try mapChainResponse(try okResponse.body.json)
            logger.info("Updated chain: \(updated.name)")
            await loadChains()
            return updated
        case .unprocessableContent(let error):
            // Preserve the engine's 422 validation detail instead of collapsing it
            // into a generic "unexpected response" (matches Automation/MCP services).
            throw ChainServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw ChainServiceError.unexpectedResponse
        }
    }

    /// Delete a chain by ID.
    func deleteChain(_ id: String) async throws {
        let response = try await apiClient.api.deleteChainApiChainsChainIdDelete(
            .init(path: .init(chainId: id))
        )
        switch response {
        case .ok:
            logger.info("Deleted chain: \(id)")
            // Remove from local list
            chains.removeAll { $0.id == id }
        case .unprocessableContent(let error):
            // Preserve the engine's 422 validation detail instead of collapsing it
            // into a generic "unexpected response" (matches Automation/MCP services).
            throw ChainServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw ChainServiceError.unexpectedResponse
        }
    }

    // MARK: - Chain Execution

    /// Execute a workflow chain.
    func executeChain(
        chainId: String,
        inputs: [String: AnyCodableValue] = [:],
        inputFiles: [String] = []
    ) async throws -> ExecuteChainResponse {
        let appRequest = ExecuteChainRequest(inputs: inputs, inputFiles: inputFiles)
        let body: Components.Schemas.ExecuteChainRequest = try encodeChainBody(appRequest)
        let response = try await apiClient.api.executeChainApiChainsChainIdExecutePost(
            .init(path: .init(chainId: chainId), body: .json(body))
        )
        switch response {
        case .ok(let okResponse):
            let result = try okResponse.body.json
            logger.info("Started chain execution: \(result.executionId)")
            return ExecuteChainResponse(
                executionId: result.executionId,
                chainId: result.chainId,
                status: result.status,
                message: result.message
            )
        case .unprocessableContent(let error):
            // Preserve the engine's 422 validation detail instead of collapsing it
            // into a generic "unexpected response" (matches Automation/MCP services).
            throw ChainServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw ChainServiceError.unexpectedResponse
        }
    }

    /// Get status of a chain execution.
    func getExecutionStatus(_ executionId: String) async throws -> ChainExecutionStatusResponse {
        let response = try await apiClient.api.getChainExecutionApiChainsExecutionsExecutionIdGet(
            .init(path: .init(executionId: executionId))
        )
        switch response {
        case .ok(let okResponse):
            return mapExecutionStatus(try okResponse.body.json)
        case .unprocessableContent(let error):
            // Preserve the engine's 422 validation detail instead of collapsing it
            // into a generic "unexpected response" (matches Automation/MCP services).
            throw ChainServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw ChainServiceError.unexpectedResponse
        }
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

// MARK: - Generated ↔ app model mappers (#3030, inline)

// The generated `Components.Schemas.Chain*` types and the app models share the
// same snake_case wire shape, so a JSON round-trip through *local* coders is a
// faithful total mapper: it preserves folder_path/sort_order (#3136) and passes
// the free-form initial_inputs / static_inputs / inputs / outputs escape through
// untouched (kept dynamic on purpose — each chain defines its own contract).
// Coders are created per call because JSONEncoder/JSONDecoder are non-Sendable
// classes; a shared global `let` would trip Swift 6 strict concurrency (same
// reason AutomationServiceMappers avoids a shared ISO8601DateFormatter).

/// Decoder whose date strategy turns the engine's ISO-ish timestamp strings
/// (`datetime.isoformat()` — microsecond precision, sometimes offset-less) into
/// `Date`. `parseEngineDate` handles every format the engine emits using local,
/// Sendable-safe formatters; `Date.ISO8601FormatStyle` alone cannot parse the
/// microsecond/offset-less variants.
private func makeChainDecoder() -> JSONDecoder {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .custom { decoder in
        let container = try decoder.singleValueContainer()
        let raw = try container.decode(String.self)
        guard let date = parseEngineDate(raw) else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Unrecognized chain timestamp: \(raw)"
            )
        }
        return date
    }
    return decoder
}

/// Map a generated `ChainResponse` (typed folder_path/sort_order post-#3136) to
/// the app `WorkflowChain` via a wire-faithful round-trip.
func mapChainResponse(_ response: Components.Schemas.ChainResponse) throws -> WorkflowChain {
    let data = try JSONEncoder().encode(response)
    return try makeChainDecoder().decode(WorkflowChain.self, from: data)
}

/// Build a generated request body of type `T` from an app `Encodable` that
/// shares the same wire shape. No chain request carries a `Date`, so the default
/// coders are correct here.
private func encodeChainBody<T: Decodable>(_ value: some Encodable) throws -> T {
    let data = try JSONEncoder().encode(value)
    return try JSONDecoder().decode(T.self, from: data)
}

/// Map a generated `ChainExecutionStatusResponse` to the app model.
///
/// Explicit (not a round-trip) because the app `ChainStepResult` carries
/// inputs/outputs/output_files that the backend's `ChainStepResultInfo` never
/// sends — defaulting them to empty here is what the backend implies and fixes a
/// latent decode failure the legacy path had on non-empty step_results.
func mapExecutionStatus(
    _ response: Components.Schemas.ChainExecutionStatusResponse
) -> ChainExecutionStatusResponse {
    ChainExecutionStatusResponse(
        executionId: response.executionId,
        chainId: response.chainId,
        status: response.status,
        stepResults: response.stepResults.map { info in
            ChainStepResult(
                stepId: info.stepId,
                workflowId: info.workflowId,
                status: ChainStepStatus(rawValue: info.status) ?? .pending,
                inputs: [:],
                outputs: [:],
                outputFiles: [],
                error: info.error,
                durationMs: info.durationMs ?? 0
            )
        },
        finalOutputs: freeformDict(response.finalOutputs),
        finalFiles: response.finalFiles ?? [],
        totalDurationMs: response.totalDurationMs ?? 0,
        events: response.events.map { event in
            ChainProgressEvent(
                eventType: event.eventType,
                stepId: event.stepId,
                message: event.message ?? "",
                progress: event.progress ?? 0,
                timestamp: event.timestamp
            )
        }
    )
}

/// Convert a generated free-form object payload (`additionalProperties: true`,
/// e.g. final_outputs) into the app's `[String: AnyCodableValue]` escape. Both
/// the nested payload struct and `OpenAPIObjectContainer` encode to a JSON
/// object, so a shape-agnostic round-trip works; a missing/undecodable payload
/// is an empty dict, never a crash.
private func freeformDict<E: Encodable>(_ value: E?) -> [String: AnyCodableValue] {
    guard let value,
          let data = try? JSONEncoder().encode(value),
          let dict = try? JSONDecoder().decode([String: AnyCodableValue].self, from: data)
    else { return [:] }
    return dict
}

// MARK: - Errors

enum ChainServiceError: LocalizedError {
    case timeout
    case notFound(String)
    case validationError(String)
    case unexpectedResponse

    var errorDescription: String? {
        switch self {
        case .timeout:
            return "Chain execution timed out"
        case .notFound(let id):
            return "Chain not found: \(id)"
        case .validationError(let message):
            return "Validation error: \(message)"
        case .unexpectedResponse:
            return "Unexpected response from the chain service"
        }
    }
}
