import Foundation
import OSLog

/// Service for model comparison API interactions
@MainActor
final class ModelComparisonService: ObservableObject {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "ModelComparisonService")

    @Published var isComparing = false
    @Published var lastResult: ComparisonResult?
    @Published var history: [ComparisonResult] = []
    @Published var presets: [ComparisonPreset] = []
    @Published var availableModels: [ComparisonModelInfo] = []
    @Published var modelsByTier: ModelsByTier?
    @Published var availableTools: [ComparisonToolInfo] = []
    @Published var error: String?

    private let baseURL = "http://localhost:8765/api/model-comparison"

    // MARK: - Compare Models

    func compare(
        prompt: String,
        models: [ModelSpec],
        systemPrompt: String? = nil
    ) async {
        isComparing = true
        error = nil

        do {
            guard let url = URL(string: "\(baseURL)/compare") else { throw ComparisonError.invalidURL }

            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.addEngineAuth()

            let body = CompareRequest(
                prompt: prompt,
                models: models.map { $0.toDict() },
                systemPrompt: systemPrompt
            )
            request.httpBody = try JSONEncoder().encode(body)

            let (data, _) = try await URLSession.shared.data(for: request)
            let result = try JSONDecoder().decode(ComparisonResult.self, from: data)

            lastResult = result
            history.insert(result, at: 0)
            logger.info("Comparison complete: \(result.comparisonId)")
        } catch {
            self.error = error.localizedDescription
            logger.error("Comparison failed: \(error.localizedDescription)")
        }

        isComparing = false
    }

    /// GET request with engine Bearer token (#742). Replaces former
    /// `URLSession.shared.data(from: url)` callsites.
    private func authedGet(_ url: URL) -> URLRequest {
        var request = URLRequest(url: url)
        request.addEngineAuth()
        return request
    }

    // MARK: - Load Available Models

    func loadModels() async {
        do {
            guard let url = URL(string: "\(baseURL)/models") else { return }
            let (data, _) = try await URLSession.shared.data(for: authedGet(url))
            let response = try JSONDecoder().decode(ComparisonModelsResponse.self, from: data)
            availableModels = response.models
        } catch {
            logger.error("Failed to load models: \(error.localizedDescription)")
        }
    }

    // MARK: - Load Presets

    func loadPresets() async {
        do {
            guard let url = URL(string: "\(baseURL)/presets") else { return }
            let (data, _) = try await URLSession.shared.data(for: authedGet(url))
            let response = try JSONDecoder().decode(PresetsResponse.self, from: data)
            presets = response.presets
        } catch {
            logger.error("Failed to load presets: \(error.localizedDescription)")
        }
    }

    // MARK: - Estimate Cost

    func estimateCost(
        prompt: String,
        models: [ModelSpec]
    ) async -> CostEstimate? {
        do {
            guard let url = URL(string: "\(baseURL)/estimate-cost") else { return nil }

            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.addEngineAuth()

            let body = CompareRequest(prompt: prompt, models: models.map { $0.toDict() })
            request.httpBody = try JSONEncoder().encode(body)

            let (data, _) = try await URLSession.shared.data(for: request)
            return try JSONDecoder().decode(CostEstimate.self, from: data)
        } catch {
            logger.error("Failed to estimate cost: \(error.localizedDescription)")
            return nil
        }
    }

    // MARK: - Load History

    func loadHistory(limit: Int = 10) async {
        do {
            guard let url = URL(string: "\(baseURL)/history?limit=\(limit)") else { return }
            let (data, _) = try await URLSession.shared.data(for: authedGet(url))
            let response = try JSONDecoder().decode(HistoryResponse.self, from: data)
            history = response.history
        } catch {
            logger.error("Failed to load history: \(error.localizedDescription)")
        }
    }

    // MARK: - Vision Comparison

    func compareVision(
        images: [String],
        prompt: String = "Describe this image in detail",
        models: [ModelSpec],
        detail: String = "auto"
    ) async {
        isComparing = true
        error = nil

        do {
            guard let url = URL(string: "\(baseURL)/compare-vision") else { throw ComparisonError.invalidURL }

            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.addEngineAuth()

            let body = VisionCompareRequest(
                images: images,
                prompt: prompt,
                models: models.map { $0.toDict() },
                detail: detail
            )
            request.httpBody = try JSONEncoder().encode(body)

            let (data, _) = try await URLSession.shared.data(for: request)
            let result = try JSONDecoder().decode(ComparisonResult.self, from: data)

            lastResult = result
            history.insert(result, at: 0)
            logger.info("Vision comparison complete: \(result.comparisonId)")
        } catch {
            self.error = error.localizedDescription
            logger.error("Vision comparison failed: \(error.localizedDescription)")
        }

        isComparing = false
    }

    // MARK: - Tool Comparison

    func compareTool(
        toolName: String,
        inputs: [String: Any],
        models: [ModelSpec],
        toolConfig: [String: Any]? = nil
    ) async {
        isComparing = true
        error = nil

        do {
            guard let url = URL(string: "\(baseURL)/compare-tool") else { throw ComparisonError.invalidURL }

            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.addEngineAuth()

            let body = ToolCompareRequest(
                toolName: toolName,
                inputs: inputs,
                models: models.map { $0.toDict() },
                toolConfig: toolConfig
            )
            request.httpBody = try JSONEncoder().encode(body)

            let (data, _) = try await URLSession.shared.data(for: request)
            let result = try JSONDecoder().decode(ComparisonResult.self, from: data)

            lastResult = result
            history.insert(result, at: 0)
            logger.info("Tool comparison complete: \(result.comparisonId)")
        } catch {
            self.error = error.localizedDescription
            logger.error("Tool comparison failed: \(error.localizedDescription)")
        }

        isComparing = false
    }

    // MARK: - Load Models By Tier

    func loadModelsByTier() async {
        do {
            guard let url = URL(string: "\(baseURL)/models-by-tier") else { return }
            let (data, _) = try await URLSession.shared.data(for: authedGet(url))
            modelsByTier = try JSONDecoder().decode(ModelsByTier.self, from: data)
        } catch {
            logger.error("Failed to load models by tier: \(error.localizedDescription)")
        }
    }

    // MARK: - Node Comparison

    func compareNode(
        workflowId: String,
        nodeId: String,
        models: [ModelSpec],
        pinnedInputs: [String: String] = [:]
    ) async throws -> NodeComparisonResponse {
        guard let url = URL(string: "\(baseURL)/compare-node") else { throw ComparisonError.invalidURL }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addEngineAuth()

        let body = NodeCompareRequest(
            workflowId: workflowId,
            nodeId: nodeId,
            models: models.map { ModelRequestSpec(provider: $0.provider, model: $0.model, temperature: $0.temperature) },
            pinnedInputs: pinnedInputs,
            timeoutSeconds: 120
        )
        request.httpBody = try JSONEncoder().encode(body)

        let (data, _) = try await URLSession.shared.data(for: request)
        let decoder = JSONDecoder()
        return try decoder.decode(NodeComparisonResponse.self, from: data)
    }

    // MARK: - Load Available Tools

    func loadTools() async {
        do {
            guard let url = URL(string: "\(baseURL)/tools") else { return }
            let (data, _) = try await URLSession.shared.data(for: authedGet(url))
            let response = try JSONDecoder().decode(ToolsResponse.self, from: data)
            availableTools = response.tools
        } catch {
            logger.error("Failed to load tools: \(error.localizedDescription)")
        }
    }
}
