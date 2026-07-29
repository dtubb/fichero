import FicheroAPIClient
import Foundation

// MARK: - Request Models

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
        let inputsData = try JSONSerialization.data(withJSONObject: inputs)
        let inputsJSON = try JSONDecoder().decode([String: ComparisonDynamicValue].self, from: inputsData)
        try container.encode(inputsJSON, forKey: .inputs)
        if let config = toolConfig {
            let configData = try JSONSerialization.data(withJSONObject: config)
            let configJSON = try JSONDecoder().decode([String: ComparisonDynamicValue].self, from: configData)
            try container.encode(configJSON, forKey: .toolConfig)
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
            value = array.map(\.value)
        } else if let dict = try? container.decode([String: ComparisonDynamicValue].self) {
            value = dict.mapValues(\.value)
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
            try container.encode(array.map(ComparisonDynamicValue.init))
        case let dict as [String: Any]:
            try container.encode(dict.mapValues(ComparisonDynamicValue.init))
        default:
            try container.encodeNil()
        }
    }
}

enum ComparisonError: LocalizedError {
    case invalidURL
    case validation(String)
    case serverError(Int)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL"
        case .validation(let detail): return detail
        case .serverError(let code): return "Server error: \(code)"
        }
    }
}

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

// MARK: - Generated Response Aliases

typealias ComparisonResult = Components.Schemas.ComparisonResultResponse
typealias ModelResult = Components.Schemas.ModelResultResponse
typealias ComparisonModelInfo = Components.Schemas.ModelInfo
typealias ComparisonModelsResponse = Components.Schemas.FicheroServerApiRoutesAiModelComparisonModelListResponse
typealias ComparisonPreset = Components.Schemas.ComparisonPreset
typealias PresetsResponse = Components.Schemas.PresetsResponse
typealias HistoryResponse = Components.Schemas.ComparisonHistoryResponse
typealias CostEstimate = Components.Schemas.CostEstimateResponse
typealias ModelCostEstimate = Components.Schemas.CostEstimateItem
typealias ModelsByTier = Components.Schemas.ModelsByTierResponse
typealias TieredModelInfo = Components.Schemas.TierModelInfo
typealias ComparisonToolInfo = Components.Schemas.ComparisonToolInfo
typealias ToolPortInfo = Components.Schemas.ToolPortInfo
typealias NodeComparisonResponse = Components.Schemas.NodeComparisonResponse
typealias NodeModelResult = Components.Schemas.ModelResultResponse
typealias NodeComparisonChoice = Components.Schemas.NodeComparisonItem

struct ToolsResponse: Codable {
    let tools: [ComparisonToolInfo]
}

extension Components.Schemas.ComparisonResultResponse: @retroactive Identifiable {
    public var id: String { comparisonId }
}

extension Components.Schemas.ModelResultResponse: @retroactive Identifiable {
    public var id: String { "\(provider)/\(model)" }
}

extension Components.Schemas.ModelInfo: @retroactive Identifiable {
    public var id: String { "\(provider)/\(model)" }
}

extension Components.Schemas.ComparisonPreset: @retroactive Identifiable {
    public var id: String { name }
}

extension Components.Schemas.TierModelInfo: @retroactive Identifiable {
    public var id: String { "\(provider)/\(model)" }
}

extension Components.Schemas.ComparisonToolInfo: @retroactive Identifiable {
    public var id: String { name }
}

extension Components.Schemas.NodeComparisonItem: @retroactive Identifiable {
    public var id: String { "\(provider)/\(model)" }
}
