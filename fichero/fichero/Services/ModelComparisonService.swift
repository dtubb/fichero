import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

/// Service for model comparison API interactions.
///
/// Routes through the generated OpenAPI client (FicheroClient → AuthTokenMiddleware
/// + LibraryPathMiddleware) instead of hand-written URLSession requests (#1666).
/// Model comparison is a **dev-tier, app-wide** feature with no library scope
/// (its sibling endpoints live under the dev feature tier), so it uses the
/// localhost client purely to carry the engine bearer token — mirroring how
/// `LocalModelsSettingsView` / `ComparisonDetailView` were migrated in #1701.
@MainActor
final class ModelComparisonService: ObservableObject {
    let logger = Logger(subsystem: "app.fichero.fichero", category: "ModelComparisonService")

    @Published var isComparing = false
    @Published var lastResult: ComparisonResult?
    @Published var history: [ComparisonResult] = []
    @Published var presets: [ComparisonPreset] = []
    @Published var availableModels: [ComparisonModelInfo] = []
    @Published var modelsByTier: ModelsByTier?
    @Published var availableTools: [ComparisonToolInfo] = []
    @Published var error: String?

    /// App-wide client (auth only, no library scope) — see type doc.
    let client: FicheroClient

    init() {
        self.client = FicheroClient.localhost
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

    func mapComparison(_ response: Components.Schemas.ComparisonResultResponse) -> ComparisonResult {
        ComparisonResult(
            prompt: response.prompt,
            modelsCompared: response.modelsCompared,
            results: response.results.map { mapModelResult($0) },
            fastestModel: response.fastestModel,
            cheapestModel: response.cheapestModel,
            totalCostUsd: response.totalCostUsd,
            totalLatencyMs: response.totalLatencyMs,
            comparisonId: response.comparisonId,
            timestamp: response.timestamp
        )
    }

    func mapModelResult(_ result: Components.Schemas.ModelResultResponse) -> ModelResult {
        ModelResult(
            provider: result.provider,
            model: result.model,
            response: result.response,
            latencyMs: result.latencyMs,
            inputTokens: result.inputTokens,
            outputTokens: result.outputTokens,
            costUsd: result.costUsd,
            error: result.error,
            timestamp: result.timestamp
        )
    }

    func mapTier(_ tier: [Components.Schemas.TierModelInfo]?) -> [TieredModelInfo] {
        (tier ?? []).map {
            TieredModelInfo(
                provider: $0.provider,
                model: $0.model,
                inputPrice: $0.inputPrice,
                outputPrice: $0.outputPrice,
                tier: $0.tier
            )
        }
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
                let result = mapComparison(try okResponse.body.json)
                lastResult = result
                history.insert(result, at: 0)
                logger.info("Comparison complete: \(result.comparisonId)")
            case .unprocessableContent:
                self.error = "Validation error"
            case .undocumented(let statusCode, _):
                self.error = "Server error: \(statusCode)"
            }
        } catch {
            self.error = error.localizedDescription
            logger.error("Comparison failed: \(error.localizedDescription)")
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
                let result = mapComparison(try okResponse.body.json)
                lastResult = result
                history.insert(result, at: 0)
                logger.info("Vision comparison complete: \(result.comparisonId)")
            case .unprocessableContent:
                self.error = "Validation error"
            case .undocumented(let statusCode, _):
                self.error = "Server error: \(statusCode)"
            }
        } catch {
            self.error = error.localizedDescription
            logger.error("Vision comparison failed: \(error.localizedDescription)")
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
                let result = mapComparison(try okResponse.body.json)
                lastResult = result
                history.insert(result, at: 0)
                logger.info("Tool comparison complete: \(result.comparisonId)")
            case .unprocessableContent:
                self.error = "Validation error"
            case .undocumented(let statusCode, _):
                self.error = "Server error: \(statusCode)"
            }
        } catch {
            self.error = error.localizedDescription
            logger.error("Tool comparison failed: \(error.localizedDescription)")
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
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? ""),
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
            let payload = try okResponse.body.json
            return NodeComparisonResponse(
                workflowId: payload.workflowId,
                nodeId: payload.nodeId,
                toolName: payload.toolName,
                choices: payload.choices.map { choice in
                    NodeComparisonChoice(
                        provider: choice.provider,
                        model: choice.model,
                        result: NodeModelResult(
                            response: choice.result.response,
                            latencyMs: choice.result.latencyMs,
                            costUsd: choice.result.costUsd,
                            error: choice.result.error
                        )
                    )
                }
            )
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
            let payload = try response.ok.body.json
            return CostEstimate(
                estimatedInputTokens: payload.estimatedInputTokens,
                estimatedOutputTokens: payload.estimatedOutputTokens,
                modelEstimates: payload.modelEstimates.map {
                    ModelCostEstimate(provider: $0.provider, model: $0.model, estimatedCostUsd: $0.estimatedCostUsd)
                },
                totalEstimatedCostUsd: payload.totalEstimatedCostUsd
            )
        } catch {
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
            let body = try response.ok.body.json
            availableModels = body.models.map {
                ComparisonModelInfo(
                    provider: $0.provider,
                    model: $0.model,
                    inputPricePerMillion: $0.inputPricePerMillion,
                    outputPricePerMillion: $0.outputPricePerMillion
                )
            }
        } catch {
            logger.error("Failed to load models: \(error.localizedDescription)")
        }
    }

    func loadPresets() async {
        do {
            let response = try await client.api.getComparisonPresetsApiModelComparisonPresetsGet()
            let body = try response.ok.body.json
            presets = body.presets.map { preset in
                ComparisonPreset(
                    name: preset.name,
                    description: preset.description,
                    models: preset.models.map { ["provider": $0.provider, "model": $0.model] }
                )
            }
        } catch {
            logger.error("Failed to load presets: \(error.localizedDescription)")
        }
    }

    func loadHistory(limit: Int = 10) async {
        do {
            let response = try await client.api.getComparisonHistoryApiModelComparisonHistoryGet(
                query: .init(limit: limit)
            )
            let body = try response.ok.body.json
            history = body.history.map { mapComparison($0) }
        } catch {
            logger.error("Failed to load history: \(error.localizedDescription)")
        }
    }

    func loadModelsByTier() async {
        do {
            let response = try await client.api.getModelsGroupedByTierApiModelComparisonModelsByTierGet()
            let payload = try response.ok.body.json
            modelsByTier = ModelsByTier(
                frontier: mapTier(payload.frontier),
                mid: mapTier(payload.mid),
                budget: mapTier(payload.budget),
                local: mapTier(payload.local)
            )
        } catch {
            logger.error("Failed to load models by tier: \(error.localizedDescription)")
        }
    }

    func loadTools() async {
        do {
            let response = try await client.api.listAvailableToolsApiModelComparisonToolsGet()
            let body = try response.ok.body.json
            availableTools = body.items.map { tool in
                ComparisonToolInfo(
                    name: tool.name,
                    displayName: tool.displayName,
                    description: tool.description,
                    category: tool.category,
                    inputPorts: tool.inputPorts.map {
                        ToolPortInfo(id: $0.id, name: $0.name, required: $0.required)
                    }
                )
            }
        } catch {
            logger.error("Failed to load tools: \(error.localizedDescription)")
        }
    }
}
