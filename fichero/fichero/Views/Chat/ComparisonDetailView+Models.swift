import Foundation

/// Full comparison detail from the API
struct ComparisonDetail: Codable, Identifiable {
    var id: String { comparisonId }
    let prompt: String
    let modelsCompared: [String]
    let results: [ModelResultDetail]
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

/// Individual model result in a comparison
struct ModelResultDetail: Codable, Identifiable {
    var id: String { "\(provider)-\(model)" }
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
        case provider
        case model
        case response
        case latencyMs = "latency_ms"
        case inputTokens = "input_tokens"
        case outputTokens = "output_tokens"
        case costUsd = "cost_usd"
        case error
        case timestamp
    }
}
