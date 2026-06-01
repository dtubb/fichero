import Foundation

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

struct ComparisonAnyCodableValue: Codable {
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

struct ComparisonModelInfo: Codable, Identifiable {
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

struct ComparisonModelsResponse: Codable {
    let models: [ComparisonModelInfo]
}

struct PresetsResponse: Codable {
    let presets: [ComparisonPreset]
}

struct HistoryResponse: Codable {
    let history: [ComparisonResult]
}

struct VisionCompareRequest: Encodable {
    let images: [String]
    let prompt: String
    let models: [[String: Any]]
    let detail: String

    enum CodingKeys: String, CodingKey {
        case images, prompt, models, detail
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(images, forKey: .images)
        try container.encode(prompt, forKey: .prompt)
        try container.encode(detail, forKey: .detail)
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

struct ToolCompareRequest: Encodable {
    let toolName: String
    let inputs: [String: Any]
    let models: [[String: Any]]
    let toolConfig: [String: Any]?

    enum CodingKeys: String, CodingKey {
        case toolName = "tool_name"
        case inputs, models
        case toolConfig = "tool_config"
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(toolName, forKey: .toolName)
        let modelSpecs = models.map { dict -> ModelRequestSpec in
            ModelRequestSpec(
                provider: dict["provider"] as? String ?? "",
                model: dict["model"] as? String ?? "",
                temperature: dict["temperature"] as? Double ?? 0.7
            )
        }
        try container.encode(modelSpecs, forKey: .models)
        // Encode inputs as JSON data
        let inputsData = try JSONSerialization.data(withJSONObject: inputs)
        let inputsJson = try JSONDecoder().decode([String: ComparisonDynamicValue].self, from: inputsData)
        try container.encode(inputsJson, forKey: .inputs)
        if let config = toolConfig {
            let configData = try JSONSerialization.data(withJSONObject: config)
            let configJson = try JSONDecoder().decode([String: ComparisonDynamicValue].self, from: configData)
            try container.encode(configJson, forKey: .toolConfig)
        }
    }
}

struct ComparisonDynamicValue: Codable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let string = try? container.decode(String.self) {
            value = string
        } else if let int = try? container.decode(Int.self) {
            value = int
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let bool = try? container.decode(Bool.self) {
            value = bool
        } else if let array = try? container.decode([ComparisonDynamicValue].self) {
            value = array.map { $0.value }
        } else if let dict = try? container.decode([String: ComparisonDynamicValue].self) {
            value = dict.mapValues { $0.value }
        } else {
            value = ""
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case let string as String:
            try container.encode(string)
        case let int as Int:
            try container.encode(int)
        case let double as Double:
            try container.encode(double)
        case let bool as Bool:
            try container.encode(bool)
        case let array as [Any]:
            try container.encode(array.map { ComparisonDynamicValue($0) })
        case let dict as [String: Any]:
            try container.encode(dict.mapValues { ComparisonDynamicValue($0) })
        default:
            try container.encodeNil()
        }
    }
}

struct ModelsByTier: Codable {
    let frontier: [TieredModelInfo]
    let mid: [TieredModelInfo]
    let budget: [TieredModelInfo]
    let local: [TieredModelInfo]
}

struct TieredModelInfo: Codable, Identifiable {
    var id: String { "\(provider)/\(model)" }
    let provider: String
    let model: String
    let inputPrice: Double
    let outputPrice: Double
    let tier: String

    enum CodingKeys: String, CodingKey {
        case provider, model, tier
        case inputPrice = "input_price"
        case outputPrice = "output_price"
    }
}

struct ComparisonToolInfo: Codable, Identifiable {
    var id: String { name }
    let name: String
    let displayName: String
    let description: String
    let category: String
    let inputPorts: [ToolPortInfo]

    enum CodingKeys: String, CodingKey {
        case name, description, category
        case displayName = "display_name"
        case inputPorts = "input_ports"
    }
}

struct ToolPortInfo: Codable {
    let id: String
    let name: String
    let required: Bool
}

struct ToolsResponse: Codable {
    let tools: [ComparisonToolInfo]
}

enum ComparisonError: LocalizedError {
    case invalidURL

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL"
        }
    }
}

// MARK: - Node Comparison

struct NodeCompareRequest: Encodable {
    let workflowId: String?
    let nodeId: String
    let models: [ModelRequestSpec]
    let pinnedInputs: [String: String]
    let timeoutSeconds: Int

    enum CodingKeys: String, CodingKey {
        case workflowId = "workflow_id"
        case nodeId = "node_id"
        case models
        case pinnedInputs = "pinned_inputs"
        case timeoutSeconds = "timeout_seconds"
    }
}

struct NodeComparisonResponse: Decodable {
    let workflowId: String?
    let nodeId: String
    let toolName: String
    let choices: [NodeComparisonChoice]

    enum CodingKeys: String, CodingKey {
        case workflowId = "workflow_id"
        case nodeId = "node_id"
        case toolName = "tool_name"
        case choices
    }
}

struct NodeModelResult: Decodable {
    let response: String
    let latencyMs: Double
    let costUsd: Double
    let error: String?

    enum CodingKeys: String, CodingKey {
        case response
        case latencyMs = "latency_ms"
        case costUsd = "cost_usd"
        case error
    }
}

struct NodeComparisonChoice: Decodable, Identifiable {
    var id: String { "\(provider)/\(model)" }
    let provider: String
    let model: String
    let result: NodeModelResult
}
