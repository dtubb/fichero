import Foundation
import OSLog

/// Service for model comparison API interactions
@MainActor
final class ModelComparisonService: ObservableObject {
    private let logger = Logger(subsystem: "com.fichero.app", category: "ModelComparisonService")

    @Published var isComparing = false
    @Published var lastResult: ComparisonResult?
    @Published var history: [ComparisonResult] = []
    @Published var presets: [ComparisonPreset] = []
    @Published var availableModels: [ModelInfo] = []
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

    // MARK: - Load Available Models

    func loadModels() async {
        do {
            guard let url = URL(string: "\(baseURL)/models") else { return }
            let (data, _) = try await URLSession.shared.data(from: url)
            let response = try JSONDecoder().decode(ModelsResponse.self, from: data)
            availableModels = response.models
        } catch {
            logger.error("Failed to load models: \(error.localizedDescription)")
        }
    }

    // MARK: - Load Presets

    func loadPresets() async {
        do {
            guard let url = URL(string: "\(baseURL)/presets") else { return }
            let (data, _) = try await URLSession.shared.data(from: url)
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
            let (data, _) = try await URLSession.shared.data(from: url)
            let response = try JSONDecoder().decode(HistoryResponse.self, from: data)
            history = response.history
        } catch {
            logger.error("Failed to load history: \(error.localizedDescription)")
        }
    }
}

// MARK: - Data Models

struct ModelSpec: Identifiable, Hashable {
    let id = UUID()
    var provider: String
    var model: String
    var temperature: Double = 0.7

    func toDict() -> [String: Any] {
        ["provider": provider, "model": model, "temperature": temperature]
    }
}

struct CompareRequest: Encodable {
    let prompt: String
    let models: [[String: Any]]
    var systemPrompt: String?

    enum CodingKeys: String, CodingKey {
        case prompt, models
        case systemPrompt = "system_prompt"
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(prompt, forKey: .prompt)
        try container.encodeIfPresent(systemPrompt, forKey: .systemPrompt)
        // Encode models as array of ModelRequestSpec
        let modelSpecs = models.map { dict -> ModelRequestSpec in
            ModelRequestSpec(
                provider: dict["provider"] as? String ?? "",
                model: dict["model"] as? String ?? "",
                temperature: dict["temperature"] as? Double ?? 0.7
            )
        }
        try container.encode(modelSpecs, forKey: .models)
    }
}

struct ModelRequestSpec: Codable {
    let provider: String
    let model: String
    let temperature: Double
}

struct AnyCodableValue: Codable {
    let value: Any

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let string = try? container.decode(String.self) {
            value = string
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let int = try? container.decode(Int.self) {
            value = int
        } else {
            value = ""
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        if let string = value as? String {
            try container.encode(string)
        } else if let double = value as? Double {
            try container.encode(double)
        } else if let int = value as? Int {
            try container.encode(int)
        }
    }
}

struct ComparisonResult: Codable, Identifiable {
    var id: String { comparisonId }
    let prompt: String
    let modelsCompared: [String]
    let results: [ModelResult]
    let fastestModel: String?
    let cheapestModel: String?
    let totalCostUsd: Double
    let totalLatencyMs: Double
    let comparisonId: String
    let timestamp: String

    enum CodingKeys: String, CodingKey {
        case prompt
        case modelsCompared = "models_compared"
        case results
        case fastestModel = "fastest_model"
        case cheapestModel = "cheapest_model"
        case totalCostUsd = "total_cost_usd"
        case totalLatencyMs = "total_latency_ms"
        case comparisonId = "comparison_id"
        case timestamp
    }
}

struct ModelResult: Codable, Identifiable {
    var id: String { "\(provider)/\(model)" }
    let provider: String
    let model: String
    let response: String
    let latencyMs: Double
    let inputTokens: Int
    let outputTokens: Int
    let costUsd: Double
    let error: String?
    let timestamp: String

    enum CodingKeys: String, CodingKey {
        case provider, model, response, error, timestamp
        case latencyMs = "latency_ms"
        case inputTokens = "input_tokens"
        case outputTokens = "output_tokens"
        case costUsd = "cost_usd"
    }
}

struct ModelInfo: Codable, Identifiable {
    var id: String { "\(provider)/\(model)" }
    let provider: String
    let model: String
    let inputPricePerMillion: Double
    let outputPricePerMillion: Double

    enum CodingKeys: String, CodingKey {
        case provider, model
        case inputPricePerMillion = "input_price_per_million"
        case outputPricePerMillion = "output_price_per_million"
    }
}

struct ComparisonPreset: Codable, Identifiable {
    var id: String { name }
    let name: String
    let description: String
    let models: [[String: String]]
}

struct CostEstimate: Codable {
    let estimatedInputTokens: Int
    let estimatedOutputTokens: Int
    let modelEstimates: [ModelCostEstimate]
    let totalEstimatedCostUsd: Double

    enum CodingKeys: String, CodingKey {
        case estimatedInputTokens = "estimated_input_tokens"
        case estimatedOutputTokens = "estimated_output_tokens"
        case modelEstimates = "model_estimates"
        case totalEstimatedCostUsd = "total_estimated_cost_usd"
    }
}

struct ModelCostEstimate: Codable {
    let provider: String
    let model: String
    let estimatedCostUsd: Double

    enum CodingKeys: String, CodingKey {
        case provider, model
        case estimatedCostUsd = "estimated_cost_usd"
    }
}

struct ModelsResponse: Codable {
    let models: [ModelInfo]
}

struct PresetsResponse: Codable {
    let presets: [ComparisonPreset]
}

struct HistoryResponse: Codable {
    let history: [ComparisonResult]
}

enum ComparisonError: LocalizedError {
    case invalidURL

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL"
        }
    }
}
