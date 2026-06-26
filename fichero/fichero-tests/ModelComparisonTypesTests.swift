@testable import Fichero
import XCTest

/// Tests for the Codable DTOs used by ModelComparisonService.
/// Locks: snake_case → camelCase decoding (Python backend contract),
/// `id` formulas for SwiftUI Identifiable (drift = silent List bugs),
/// custom encoders for [String: Any] request bodies.
final class ModelComparisonTypesTests: XCTestCase {

    // MARK: - ModelSpec

    func testModelSpecDefaultTemperature() {
        let spec = ModelSpec(provider: "openai", model: "gpt-4o")
        XCTAssertEqual(spec.temperature, 0.7)
    }

    func testModelSpecToDictShape() {
        let spec = ModelSpec(provider: "openai", model: "gpt-4o", temperature: 0.5)
        let dict = spec.toDict()
        XCTAssertEqual(dict["provider"] as? String, "openai")
        XCTAssertEqual(dict["model"] as? String, "gpt-4o")
        XCTAssertEqual(dict["temperature"] as? Double, 0.5)
    }

    // MARK: - CompareRequest encoding

    func testCompareRequestEncodesModelsAsArray() throws {
        let req = CompareRequest(
            prompt: "hello",
            models: [["provider": "openai", "model": "gpt-4o", "temperature": 0.7]],
            systemPrompt: "sys"
        )
        let data = try JSONEncoder().encode(req)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["prompt"] as? String, "hello")
        XCTAssertEqual(json?["system_prompt"] as? String, "sys")  // snake_case key
        let models = json?["models"] as? [[String: Any]]
        XCTAssertEqual(models?.count, 1)
        XCTAssertEqual(models?.first?["provider"] as? String, "openai")
    }

    func testCompareRequestOmitsNilSystemPrompt() throws {
        let req = CompareRequest(prompt: "x", models: [], systemPrompt: nil)
        let data = try JSONEncoder().encode(req)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertNil(json?["system_prompt"])
    }

    // MARK: - ComparisonResult snake_case decode

    func testComparisonResultDecodesSnakeCase() throws {
        let json = """
        {
            "prompt": "test",
            "models_compared": ["openai/gpt-4o"],
            "results": [],
            "fastest_model": "openai/gpt-4o",
            "cheapest_model": "openai/gpt-4o",
            "total_cost_usd": 0.05,
            "total_latency_ms": 1234.5,
            "comparison_id": "abc-123",
            "timestamp": "2026-05-10T10:00:00Z"
        }
        """.data(using: .utf8)!
        let result = try JSONDecoder().decode(Fichero.ComparisonResult.self, from: json)
        XCTAssertEqual(result.modelsCompared, ["openai/gpt-4o"])
        XCTAssertEqual(result.fastestModel, "openai/gpt-4o")
        XCTAssertEqual(result.totalCostUsd, 0.05)
        XCTAssertEqual(result.totalLatencyMs, 1234.5)
        XCTAssertEqual(result.comparisonId, "abc-123")
        XCTAssertEqual(result.id, "abc-123")  // id derived from comparisonId
    }

    // MARK: - ModelResult

    func testModelResultIdFormula() throws {
        let json = """
        {
            "provider": "anthropic",
            "model": "claude-opus",
            "response": "...",
            "latency_ms": 100.0,
            "input_tokens": 50,
            "output_tokens": 200,
            "cost_usd": 0.01,
            "error": null,
            "timestamp": "2026-05-10T10:00:00Z"
        }
        """.data(using: .utf8)!
        let result = try JSONDecoder().decode(ModelResult.self, from: json)
        XCTAssertEqual(result.id, "anthropic/claude-opus")  // SwiftUI Identifiable key
        XCTAssertEqual(result.inputTokens, 50)
        XCTAssertEqual(result.outputTokens, 200)
        XCTAssertEqual(result.costUsd, 0.01)
        XCTAssertNil(result.error)
    }

    // MARK: - ComparisonModelInfo

    func testComparisonModelInfoDecodesPriceFields() throws {
        let json = """
        {
            "provider": "openai",
            "model": "gpt-4o",
            "input_price_per_million": 2.5,
            "output_price_per_million": 10.0
        }
        """.data(using: .utf8)!
        let info = try JSONDecoder().decode(ComparisonModelInfo.self, from: json)
        XCTAssertEqual(info.id, "openai/gpt-4o")
        XCTAssertEqual(info.inputPricePerMillion, 2.5)
        XCTAssertEqual(info.outputPricePerMillion, 10.0)
    }

    // MARK: - CostEstimate

    func testCostEstimateDecodes() throws {
        let json = """
        {
            "estimated_input_tokens": 100,
            "estimated_output_tokens": 500,
            "model_estimates": [],
            "total_estimated_cost_usd": 0.02
        }
        """.data(using: .utf8)!
        let est = try JSONDecoder().decode(CostEstimate.self, from: json)
        XCTAssertEqual(est.estimatedInputTokens, 100)
        XCTAssertEqual(est.estimatedOutputTokens, 500)
        XCTAssertEqual(est.totalEstimatedCostUsd, 0.02)
    }

    // MARK: - TieredModelInfo

    func testTieredModelInfoSnakeCaseAndId() throws {
        let json = """
        {
            "provider": "google",
            "model": "gemini-pro",
            "input_price": 0.5,
            "output_price": 1.5,
            "tier": "mid"
        }
        """.data(using: .utf8)!
        let info = try JSONDecoder().decode(TieredModelInfo.self, from: json)
        XCTAssertEqual(info.id, "google/gemini-pro")
        XCTAssertEqual(info.inputPrice, 0.5)
        XCTAssertEqual(info.tier, "mid")
    }

    func testModelsByTierDecodesAllBuckets() throws {
        let json = """
        {
            "frontier": [],
            "mid": [],
            "budget": [],
            "local": []
        }
        """.data(using: .utf8)!
        let bucket = try JSONDecoder().decode(ModelsByTier.self, from: json)
        XCTAssertEqual(bucket.frontier ?? [], [])
        XCTAssertEqual(bucket.mid ?? [], [])
        XCTAssertEqual(bucket.budget ?? [], [])
        XCTAssertEqual(bucket.local ?? [], [])
    }

    // MARK: - ComparisonToolInfo

    func testComparisonToolInfoDecodes() throws {
        let json = """
        {
            "name": "summarize",
            "display_name": "Summarize",
            "description": "Summarises documents",
            "category": "ai",
            "input_ports": [
                {"id": "text", "name": "Text", "required": true}
            ]
        }
        """.data(using: .utf8)!
        let tool = try JSONDecoder().decode(ComparisonToolInfo.self, from: json)
        XCTAssertEqual(tool.id, "summarize")  // id is name
        XCTAssertEqual(tool.displayName, "Summarize")
        XCTAssertEqual(tool.inputPorts.count, 1)
        XCTAssertTrue(tool.inputPorts.first?.required ?? false)
    }

    // MARK: - ComparisonDynamicValue round-trip

    func testDynamicValueRoundTripString() throws {
        let original = ComparisonDynamicValue("hello")
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(ComparisonDynamicValue.self, from: data)
        XCTAssertEqual(decoded.value as? String, "hello")
    }

    func testDynamicValueRoundTripInt() throws {
        let original = ComparisonDynamicValue(42)
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(ComparisonDynamicValue.self, from: data)
        XCTAssertEqual(decoded.value as? Int, 42)
    }

    func testDynamicValueRoundTripBool() throws {
        let original = ComparisonDynamicValue(true)
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(ComparisonDynamicValue.self, from: data)
        XCTAssertEqual(decoded.value as? Bool, true)
    }

    func testDynamicValueRoundTripArray() throws {
        let original = ComparisonDynamicValue(["a", "b"] as [Any])
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(ComparisonDynamicValue.self, from: data)
        let arr = decoded.value as? [Any]
        XCTAssertEqual(arr?.count, 2)
        XCTAssertEqual(arr?[0] as? String, "a")
    }

    func testDynamicValueDecodesUnknownAsEmptyString() throws {
        // Decoder's fallback branch when no kind matches — exercises
        // the safety hatch in init(from:).
        let data = "null".data(using: .utf8)!
        let decoded = try JSONDecoder().decode(ComparisonDynamicValue.self, from: data)
        XCTAssertEqual(decoded.value as? String, "")
    }

    // MARK: - ComparisonError

    func testComparisonErrorDescription() {
        XCTAssertEqual(ComparisonError.invalidURL.errorDescription, "Invalid URL")
    }

    // MARK: - Wrapper response shapes

    func testToolsResponseDecodes() throws {
        let json = """
        {"tools": []}
        """.data(using: .utf8)!
        let resp = try JSONDecoder().decode(ToolsResponse.self, from: json)
        XCTAssertTrue(resp.tools.isEmpty)
    }

    func testPresetsResponseDecodes() throws {
        let json = """
        {"presets": [{"name": "Quick", "description": "fast", "models": []}]}
        """.data(using: .utf8)!
        let resp = try JSONDecoder().decode(PresetsResponse.self, from: json)
        XCTAssertEqual(resp.presets.count, 1)
        XCTAssertEqual(resp.presets.first?.id, "Quick")  // id is name
    }
}
