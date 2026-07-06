@testable import Fichero
import XCTest

/// Covers the model-comparison request encoders that ModelComparisonTypesTests
/// leaves untested: the three custom `encode(to:)` request builders
/// (Vision/Tool/Node) plus the ComparisonAnyCodableValue codec. These turn
/// loosely-typed `[String: Any]` dicts into the exact wire body the backend
/// expects, so their key mapping and defaulting is pure, headless logic.
final class ModelComparisonRequestEncodingTests: XCTestCase {

    private func encodeToDict<T: Encodable>(_ value: T) throws -> [String: Any] {
        let data = try JSONEncoder().encode(value)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    // MARK: - ComparisonAnyCodableValue (decode → re-encode round-trip)

    func testAnyCodableValueRoundTripsString() throws {
        let decoded = try JSONDecoder().decode(ComparisonAnyCodableValue.self,
                                               from: Data("\"hello\"".utf8))
        let out = try JSONEncoder().encode(decoded)
        XCTAssertEqual(String(data: out, encoding: .utf8), "\"hello\"")
    }

    func testAnyCodableValueDecodesNumberAsDouble() throws {
        // Double is attempted before Int, so any JSON number becomes Double.
        let decoded = try JSONDecoder().decode(ComparisonAnyCodableValue.self,
                                               from: Data("5".utf8))
        XCTAssertTrue(decoded.value is Double, "number should decode as Double")
        let out = try JSONEncoder().encode(decoded)
        XCTAssertEqual(String(data: out, encoding: .utf8), "5.0")
    }

    func testAnyCodableValueUnsupportedTypeFallsBackToEmptyString() throws {
        // A bool is neither String nor a number → the else branch stores "".
        let decoded = try JSONDecoder().decode(ComparisonAnyCodableValue.self,
                                               from: Data("true".utf8))
        XCTAssertEqual(decoded.value as? String, "")
        let out = try JSONEncoder().encode(decoded)
        XCTAssertEqual(String(data: out, encoding: .utf8), "\"\"")
    }

    // MARK: - VisionCompareRequest.encode

    func testVisionRequestEncodesScalarsAndMapsModelDefaults() throws {
        let req = VisionCompareRequest(
            images: ["b64-a", "b64-b"],
            prompt: "describe",
            models: [
                ["provider": "openai", "model": "gpt", "temperature": 0.3],
                ["model": "claude"]  // missing provider + temperature → defaults
            ],
            detail: "high"
        )
        let obj = try encodeToDict(req)
        XCTAssertEqual(obj["images"] as? [String], ["b64-a", "b64-b"])
        XCTAssertEqual(obj["prompt"] as? String, "describe")
        XCTAssertEqual(obj["detail"] as? String, "high")

        let models = try XCTUnwrap(obj["models"] as? [[String: Any]])
        XCTAssertEqual(models.count, 2)
        XCTAssertEqual(models[0]["provider"] as? String, "openai")
        XCTAssertEqual(models[0]["model"] as? String, "gpt")
        XCTAssertEqual(models[0]["temperature"] as? Double, 0.3)
        // Defaults applied for the sparse dict.
        XCTAssertEqual(models[1]["provider"] as? String, "")
        XCTAssertEqual(models[1]["model"] as? String, "claude")
        XCTAssertEqual(models[1]["temperature"] as? Double, 0.7)
    }

    // MARK: - ToolCompareRequest.encode

    func testToolRequestEncodesSnakeCaseAndOmitsNilConfig() throws {
        let req = ToolCompareRequest(
            toolName: "web_search",
            inputs: ["query": "hi", "limit": 3],
            models: [["provider": "p", "model": "m", "temperature": 0.5]],
            toolConfig: nil
        )
        let obj = try encodeToDict(req)
        XCTAssertEqual(obj["tool_name"] as? String, "web_search")
        XCTAssertNil(obj["tool_config"], "nil tool_config must be omitted")

        let inputs = try XCTUnwrap(obj["inputs"] as? [String: Any])
        XCTAssertEqual(inputs["query"] as? String, "hi")
        XCTAssertEqual(inputs["limit"] as? Int, 3)

        let models = try XCTUnwrap(obj["models"] as? [[String: Any]])
        XCTAssertEqual(models[0]["temperature"] as? Double, 0.5)
    }

    func testToolRequestEncodesToolConfigWhenPresent() throws {
        let req = ToolCompareRequest(
            toolName: "t",
            inputs: [:],
            models: [],
            toolConfig: ["max_tokens": 128, "stream": true]
        )
        let obj = try encodeToDict(req)
        let config = try XCTUnwrap(obj["tool_config"] as? [String: Any])
        XCTAssertEqual(config["max_tokens"] as? Int, 128)
        XCTAssertEqual(config["stream"] as? Bool, true)
    }

    // MARK: - NodeCompareRequest (synthesized encode, snake_case keys)

    func testNodeRequestEncodesSnakeCaseKeys() throws {
        let req = NodeCompareRequest(
            workflowId: "wf-1",
            nodeId: "node-9",
            models: [ModelRequestSpec(provider: "p", model: "m", temperature: 0.7)],
            pinnedInputs: ["a": "b"],
            timeoutSeconds: 30
        )
        let obj = try encodeToDict(req)
        XCTAssertEqual(obj["workflow_id"] as? String, "wf-1")
        XCTAssertEqual(obj["node_id"] as? String, "node-9")
        XCTAssertEqual(obj["timeout_seconds"] as? Int, 30)
        XCTAssertEqual(obj["pinned_inputs"] as? [String: String], ["a": "b"])
    }

    func testNodeRequestOmitsNilWorkflowId() throws {
        let req = NodeCompareRequest(
            workflowId: nil,
            nodeId: "node-1",
            models: [],
            pinnedInputs: [:],
            timeoutSeconds: 10
        )
        let obj = try encodeToDict(req)
        XCTAssertNil(obj["workflow_id"], "nil workflowId must be omitted, not encoded as null")
        XCTAssertEqual(obj["node_id"] as? String, "node-1")
    }
}
