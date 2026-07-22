import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

/// Service for model comparison API interactions.
///
/// Routes through the generated OpenAPI client (FicheroClient → AuthTokenMiddleware
/// + LibraryPathMiddleware) instead of hand-written URLSession requests (#1666).
/// Model comparison is a **dev-tier, app-wide** feature with no library scope
/// (its sibling endpoints live under the dev feature tier), so it uses the
/// configured engine client purely to carry the engine bearer token — mirroring
/// how `LocalModelsSettingsView` / `ComparisonDetailView` were migrated in #1701.
@MainActor
@Observable
final class ModelComparisonService {
    let logger = Logger(subsystem: "app.fichero.fichero", category: "ModelComparisonService")
    // @ObservationIgnored so the @Observable macro doesn't wrap this in tracked
    // storage — that's what made `nonisolated(unsafe)` "have no effect" (#3977) and
    // why plain `nonisolated` won't compile on the mutable stored property. With it
    // ignored, `nonisolated(unsafe)` is effective and lets `deinit` read it.
    @ObservationIgnored private nonisolated(unsafe) var hostChangeObservation: NSObjectProtocol?

    var isComparing = false
    var lastResult: ComparisonResult?
    var history: [ComparisonResult] = []
    var presets: [ComparisonPreset] = []
    var availableModels: [ComparisonModelInfo] = []
    var modelsByTier: ModelsByTier?
    var availableTools: [ComparisonToolInfo] = []
    var error: String?

    /// App-wide client (auth only, no library scope) — see type doc.
    let client: FicheroClient

    init() {
        self.client = FicheroClient(baseURL: EngineConfig.host, transportMode: EngineConfig.transportMode)
        hostChangeObservation = NotificationCenter.default.addObserver(
            forName: EngineConfig.engineHostDidChangeNotification,
            object: nil,
            queue: nil
        ) { [weak self] _ in
            Task { @MainActor in
                self?.reconfigureBackendHost()
            }
        }
    }

    deinit {
        if let hostChangeObservation {
            NotificationCenter.default.removeObserver(hostChangeObservation)
        }
    }

    func reconfigureBackendHost() {
        client.reconfigure(baseURL: EngineConfig.host)
    }
}

// MARK: - Request / Response Helpers

private extension ModelComparisonService {
    /// Build the free-form model-spec object the backend expects for each
    /// model in a comparison request (provider / model / temperature).
    func modelContainer(_ spec: ModelSpec) throws -> OpenAPIRuntime.OpenAPIObjectContainer {
        let dict: [String: any Sendable] = [
            "provider": spec.provider,
            "model": spec.model,
            "temperature": spec.temperature
        ]
        return try OpenAPIObjectContainer(unvalidatedValue: dict)
    }

    /// Build an `OpenAPIObjectContainer` from an arbitrary JSON-compatible
    /// dictionary (inputs / tool config). Round-trips through JSONSerialization
    /// to preserve the previous URLSession encoding behaviour exactly.
    func objectContainer(fromJSON dict: [String: Any]) throws -> OpenAPIRuntime.OpenAPIObjectContainer {
        let data = try JSONSerialization.data(withJSONObject: dict)
        return try JSONDecoder().decode(OpenAPIRuntime.OpenAPIObjectContainer.self, from: data)
    }

}

// MARK: - Comparison Operations

extension ModelComparisonService {
    // MARK: Compare Models

    func compare(
        prompt: String,
        models: [ModelSpec],
        systemPrompt: String? = nil
    ) async {
        isComparing = true
        error = nil

        do {
            let modelsPayload: Components.Schemas.CompareRequest.ModelsPayload = try models.map {
                .init(additionalProperties: try modelContainer($0))
            }
            let response = try await client.api.compareModelsApiModelComparisonComparePost(
                body: .json(.init(prompt: prompt, models: modelsPayload, systemPrompt: systemPrompt))
            )

            switch response {
            case .ok(let okResponse):
                let result = try okResponse.body.json
                lastResult = result
                history.insert(result, at: 0)
                logger.info("Comparison complete: \(result.comparisonId)")
            case .unprocessableContent:
                self.error = "Validation error"
            case .undocumented(let statusCode, _):
                self.error = "Server error: \(statusCode)"
            }
        } catch {
            // Superseded/cancelled comparison is not a failure — skip logging and
            // the error state, but still clear `isComparing` below.
            if !error.isCancellationError {
                self.error = error.localizedDescription
                logger.error("Comparison failed: \(error.localizedDescription)")
            }
        }

        isComparing = false
    }

    // MARK: Vision Comparison

    func compareVision(
        images: [String],
        prompt: String = "Describe this image in detail",
        models: [ModelSpec],
        detail: String = "auto"
    ) async {
        isComparing = true
        error = nil

        do {
            let modelsPayload: Components.Schemas.VisionCompareRequest.ModelsPayload = try models.map {
                .init(additionalProperties: try modelContainer($0))
            }
            let response = try await client.api.compareVisionModelsApiModelComparisonCompareVisionPost(
                body: .json(.init(images: images, prompt: prompt, models: modelsPayload, detail: detail))
            )

            switch response {
            case .ok(let okResponse):
                let result = try okResponse.body.json
                lastResult = result
                history.insert(result, at: 0)
                logger.info("Vision comparison complete: \(result.comparisonId)")
            case .unprocessableContent:
                self.error = "Validation error"
            case .undocumented(let statusCode, _):
                self.error = "Server error: \(statusCode)"
            }
        } catch {
            if !error.isCancellationError {
                self.error = error.localizedDescription
                logger.error("Vision comparison failed: \(error.localizedDescription)")
            }
        }

        isComparing = false
    }

    // MARK: Tool Comparison

    func compareTool(
        toolName: String,
        inputs: [String: Any],
        models: [ModelSpec],
        toolConfig: [String: Any]? = nil
    ) async {
        isComparing = true
        error = nil

        do {
            let modelsPayload: Components.Schemas.ToolCompareRequest.ModelsPayload = try models.map {
                .init(additionalProperties: try modelContainer($0))
            }
            let inputsPayload = Components.Schemas.ToolCompareRequest.InputsPayload(
                additionalProperties: try objectContainer(fromJSON: inputs)
            )
            let toolConfigPayload = try toolConfig.map {
                Components.Schemas.ToolCompareRequest.ToolConfigPayload(
                    additionalProperties: try objectContainer(fromJSON: $0)
                )
            }
            let response = try await client.api.compareToolAcrossModelsApiModelComparisonCompareToolPost(
                body: .json(.init(
                    toolName: toolName,
                    inputs: inputsPayload,
                    models: modelsPayload,
                    toolConfig: toolConfigPayload
                ))
            )

            switch response {
            case .ok(let okResponse):
                let result = try okResponse.body.json
                lastResult = result
                history.insert(result, at: 0)
                logger.info("Tool comparison complete: \(result.comparisonId)")
            case .unprocessableContent:
                self.error = "Validation error"
            case .undocumented(let statusCode, _):
                self.error = "Server error: \(statusCode)"
            }
        } catch {
            if !error.isCancellationError {
                self.error = error.localizedDescription
                logger.error("Tool comparison failed: \(error.localizedDescription)")
            }
        }

        isComparing = false
    }

    // MARK: Node Comparison

    func compareNode(
        workflowId: String,
        nodeId: String,
        models: [ModelSpec],
        pinnedInputs: [String: String] = [:]
    ) async throws -> NodeComparisonResponse {
        let modelsPayload: Components.Schemas.NodeCompareRequest.ModelsPayload = try models.map {
            .init(additionalProperties: try modelContainer($0))
        }
        let pinnedPayload = Components.Schemas.NodeCompareRequest.PinnedInputsPayload(
            additionalProperties: try objectContainer(fromJSON: pinnedInputs.mapValues { $0 as Any })
        )
        // compare-node is library-scoped (a workflow node lives in a library),
        // unlike the other app-wide comparison endpoints — pass the current
        // library path, matching SavedSearch/Chat/Note services.
        let response = try await client.api.compareWorkflowNodeApiModelComparisonCompareNodePost(
            body: .json(.init(
                workflowId: workflowId,
                nodeId: nodeId,
                models: modelsPayload,
                pinnedInputs: pinnedPayload,
                timeoutSeconds: 120
            ))
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent:
            throw ComparisonError.validation("Validation error")
        case .undocumented(let statusCode, _):
            throw ComparisonError.serverError(statusCode)
        }
    }

    // MARK: Estimate Cost

    func estimateCost(
        prompt: String,
        models: [ModelSpec]
    ) async -> CostEstimate? {
        do {
            let modelsPayload: Components.Schemas.CompareRequest.ModelsPayload = try models.map {
                .init(additionalProperties: try modelContainer($0))
            }
            let response = try await client.api.estimateComparisonCostApiModelComparisonEstimateCostPost(
                body: .json(.init(prompt: prompt, models: modelsPayload))
            )
            return try response.ok.body.json
        } catch {
            if error.isCancellationError { return nil }   // superseded — not a failure
            logger.error("Failed to estimate cost: \(error.localizedDescription)")
            return nil
        }
    }
}

// MARK: - Catalog Loaders

extension ModelComparisonService {
    func loadModels() async {
        do {
            let response = try await client.api.listAvailableModelsApiModelComparisonModelsGet()
            availableModels = try response.ok.body.json.models
        } catch {
            if error.isCancellationError { return }   // superseded — not a failure
            logger.error("Failed to load models: \(error.localizedDescription)")
        }
    }

    func loadPresets() async {
        do {
            let response = try await client.api.getComparisonPresetsApiModelComparisonPresetsGet()
            presets = try response.ok.body.json.presets
        } catch {
            if error.isCancellationError { return }   // superseded — not a failure
            logger.error("Failed to load presets: \(error.localizedDescription)")
        }
    }

    func loadHistory(limit: Int = 10) async {
        do {
            let response = try await client.api.getComparisonHistoryApiModelComparisonHistoryGet(
                query: .init(limit: limit)
            )
            history = try response.ok.body.json.history
        } catch {
            if error.isCancellationError { return }   // superseded — not a failure
            logger.error("Failed to load history: \(error.localizedDescription)")
        }
    }

    func loadModelsByTier() async {
        do {
            let response = try await client.api.getModelsGroupedByTierApiModelComparisonModelsByTierGet()
            modelsByTier = try response.ok.body.json
        } catch {
            if error.isCancellationError { return }   // superseded — not a failure
            logger.error("Failed to load models by tier: \(error.localizedDescription)")
        }
    }

    func loadTools() async {
        do {
            let response = try await client.api.listAvailableToolsApiModelComparisonToolsGet()
            availableTools = try response.ok.body.json.items
        } catch {
            if error.isCancellationError { return }   // superseded — not a failure
            logger.error("Failed to load tools: \(error.localizedDescription)")
        }
    }
}
