@testable import Fichero
import XCTest

/// Tests for WorkflowToolTypes — the tool-palette + node-config
/// DTOs the workflow editor pulls from /api/workflows/tools. Locks
/// every snake_case key, the type-erased AnyCodableValue codec, and
/// the PortInfo defaulting rules (required=true, description="").
final class WorkflowToolTypesTests: XCTestCase {

    // MARK: - CategoryTools / ToolInfo decode

    func testCategoryToolsDecodesSnakeCase() throws {
        let json = """
        {
            "category": "vision",
            "display_name": "Vision",
            "tools": []
        }
        """.data(using: .utf8)!
        let category = try JSONDecoder().decode(CategoryTools.self, from: json)
        XCTAssertEqual(category.id, "vision")  // id == category
        XCTAssertEqual(category.displayName, "Vision")
        XCTAssertTrue(category.tools.isEmpty)
    }

    func testToolInfoDecodesEveryField() throws {
        let json = """
        {
            "name": "summarize",
            "display_name": "Summarize",
            "description": "Summarise text",
            "category": "ai",
            "icon": "doc.text",
            "color": "blue",
            "input_ports": [],
            "output_ports": [],
            "config_schema": {},
            "config_defaults": {"temperature": 0.7},
            "default_output_schema": null,
            "default_prompt": "Summarise the following text.",
            "uses_llm": true,
            "supports_batch": false,
            "supports_streaming": true,
            "supports_structured_output": false,
            "sort_order": 5
        }
        """.data(using: .utf8)!
        let tool = try JSONDecoder().decode(ToolInfo.self, from: json)
        XCTAssertEqual(tool.id, "summarize")  // id == name
        XCTAssertEqual(tool.displayName, "Summarize")
        XCTAssertTrue(tool.usesLLM)
        XCTAssertFalse(tool.supportsBatch)
        XCTAssertTrue(tool.supportsStreaming)
        XCTAssertEqual(tool.sortOrder, 5)
        XCTAssertNil(tool.defaultOutputSchema)
        XCTAssertEqual(tool.defaultPrompt, "Summarise the following text.")
        if case .double(let temp) = tool.configDefaults["temperature"] {
            XCTAssertEqual(temp, 0.7)
        } else {
            XCTFail("Expected .double for temperature default")
        }
    }

    // MARK: - AnyCodableValue per-branch decode

    func testAnyCodableValueDecodesString() throws {
        let data = "\"hello\"".data(using: .utf8)!
        let value = try JSONDecoder().decode(AnyCodableValue.self, from: data)
        if case .string(let s) = value { XCTAssertEqual(s, "hello") } else { XCTFail() }
    }

    func testAnyCodableValueDecodesInt() throws {
        let data = "42".data(using: .utf8)!
        let value = try JSONDecoder().decode(AnyCodableValue.self, from: data)
        if case .int(let i) = value { XCTAssertEqual(i, 42) } else { XCTFail() }
    }

    func testAnyCodableValueDecodesDoubleNotInt() throws {
        // 3.14 must decode as .double, not somehow as .int (the order in
        // init(from:) matters — String, then Int, then Double).
        let data = "3.14".data(using: .utf8)!
        let value = try JSONDecoder().decode(AnyCodableValue.self, from: data)
        if case .double(let d) = value { XCTAssertEqual(d, 3.14) } else { XCTFail() }
    }

    func testAnyCodableValueDecodesBool() throws {
        let data = "true".data(using: .utf8)!
        let value = try JSONDecoder().decode(AnyCodableValue.self, from: data)
        if case .bool(let b) = value { XCTAssertTrue(b) } else { XCTFail() }
    }

    func testAnyCodableValueDecodesArray() throws {
        let data = "[1, \"two\", null]".data(using: .utf8)!
        let value = try JSONDecoder().decode(AnyCodableValue.self, from: data)
        guard case .array(let arr) = value else {
            XCTFail("Expected .array")
            return
        }
        XCTAssertEqual(arr.count, 3)
        if case .int(let n) = arr[0] { XCTAssertEqual(n, 1) } else { XCTFail() }
        if case .string(let s) = arr[1] { XCTAssertEqual(s, "two") } else { XCTFail() }
        if case .null = arr[2] {} else { XCTFail("Expected .null") }
    }

    func testAnyCodableValueDecodesDictionary() throws {
        let data = "{\"a\": 1, \"b\": false}".data(using: .utf8)!
        let value = try JSONDecoder().decode(AnyCodableValue.self, from: data)
        guard case .dictionary(let dict) = value else {
            XCTFail("Expected .dictionary")
            return
        }
        XCTAssertEqual(dict.count, 2)
        if case .int(let n) = dict["a"] { XCTAssertEqual(n, 1) } else { XCTFail() }
        if case .bool(let b) = dict["b"] { XCTAssertFalse(b) } else { XCTFail() }
    }

    func testAnyCodableValueDecodesNull() throws {
        let data = "null".data(using: .utf8)!
        let value = try JSONDecoder().decode(AnyCodableValue.self, from: data)
        if case .null = value {} else { XCTFail("Expected .null") }
    }

    // MARK: - AnyCodableValue encode round-trip

    func testAnyCodableValueRoundTripsEveryBranch() throws {
        let values: [AnyCodableValue] = [
            .string("hi"),
            .int(7),
            .double(2.5),
            .bool(true),
            .array([.int(1), .string("two")]),
            .dictionary(["k": .string("v")]),
            .null
        ]
        let encoder = JSONEncoder()
        let decoder = JSONDecoder()
        for value in values {
            let data = try encoder.encode(value)
            let decoded = try decoder.decode(AnyCodableValue.self, from: data)
            XCTAssertEqual(decoded, value)  // Hashable + Equatable required
        }
    }

    // MARK: - PortInfo

    func testPortInfoMemberwiseInitDefaults() {
        let port = PortInfo(id: "in", name: "Input", portType: "input", dataType: "text")
        XCTAssertTrue(port.required)            // default
        XCTAssertEqual(port.description, "")    // default
        XCTAssertNil(port.defaultValue)
        XCTAssertTrue(port.isInput)
        XCTAssertFalse(port.isOutput)
    }

    func testPortInfoOutputClassification() {
        let port = PortInfo(id: "out", name: "Output", portType: "output", dataType: "text")
        XCTAssertFalse(port.isInput)
        XCTAssertTrue(port.isOutput)
    }

    func testPortInfoDecodesSnakeCase() throws {
        let json = """
        {
            "id": "p", "name": "Port",
            "port_type": "input",
            "data_type": "text",
            "required": false,
            "description": "An input",
            "default": "fallback"
        }
        """.data(using: .utf8)!
        let port = try JSONDecoder().decode(PortInfo.self, from: json)
        XCTAssertEqual(port.portType, "input")
        XCTAssertEqual(port.dataType, "text")
        XCTAssertFalse(port.required)
        XCTAssertEqual(port.description, "An input")
        if case .string(let s) = port.defaultValue { XCTAssertEqual(s, "fallback") } else { XCTFail() }
    }

    func testPortInfoCustomDecoderFillsMissingDefaults() throws {
        // The backend may omit `required`, `description`, `default`.
        // Custom init(from:) must supply: required=true, description="".
        let json = """
        {
            "id": "p", "name": "Port",
            "port_type": "output",
            "data_type": "text"
        }
        """.data(using: .utf8)!
        let port = try JSONDecoder().decode(PortInfo.self, from: json)
        XCTAssertTrue(port.required)
        XCTAssertEqual(port.description, "")
        XCTAssertNil(port.defaultValue)
        XCTAssertTrue(port.isOutput)
    }

    func testPortInfoEncodingPreservesSnakeCase() throws {
        let port = PortInfo(
            id: "p", name: "Port",
            portType: "input", dataType: "text",
            required: false, description: "x",
            defaultValue: .string("d")
        )
        let data = try JSONEncoder().encode(port)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["port_type"] as? String, "input")
        XCTAssertEqual(json?["data_type"] as? String, "text")
        // `default` is the JSON key for defaultValue
        XCTAssertNotNil(json?["default"])
    }
}
