@testable import Fichero
import Foundation
import XCTest

/// Tests for WorkflowSupportTypes — OutputSchema, InputMapping,
/// AgentType. Locks the JSON Codable contract (load-bearing for
/// workflow round-trip with the Python backend) + AgentType cases.
final class WorkflowSupportTypesTests: XCTestCase {

    // MARK: - OutputSchema

    func testOutputSchemaDefaultDescription() {
        let schema = OutputSchema(jsonSchema: [:])
        XCTAssertEqual(schema.description, "")
    }

    func testOutputSchemaSnakeCaseAliasOnEncode() throws {
        let schema = OutputSchema(
            jsonSchema: ["type": .string("object")],
            description: "A test schema"
        )
        let data = try JSONEncoder().encode(schema)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        // The key in JSON is "schema" (alias for json_schema). The user/
        // backend round-trip depends on this exact spelling.
        XCTAssertNotNil(json?["schema"])
        XCTAssertEqual(json?["description"] as? String, "A test schema")
    }

    func testOutputSchemaDecodesPopulatedFields() throws {
        let data = """
        {
            "schema": {"type": "object"},
            "description": "Test"
        }
        """.data(using: .utf8)!
        let schema = try JSONDecoder().decode(OutputSchema.self, from: data)
        XCTAssertEqual(schema.description, "Test")
        XCTAssertEqual(schema.jsonSchema.count, 1)
    }

    func testOutputSchemaDecodesMissingFieldsAsDefaults() throws {
        // Backend may omit description or schema. Custom init(from:)
        // must supply: jsonSchema = [:], description = "".
        let data = "{}".data(using: .utf8)!
        let schema = try JSONDecoder().decode(OutputSchema.self, from: data)
        XCTAssertTrue(schema.jsonSchema.isEmpty)
        XCTAssertEqual(schema.description, "")
    }

    // MARK: - InputMapping

    func testInputMappingIdIsPortId() {
        let mapping = InputMapping(portId: "p1", sourcePath: "out.text")
        XCTAssertEqual(mapping.id, "p1")
        XCTAssertEqual(mapping.portId, "p1")
        XCTAssertNil(mapping.transform)
    }

    func testInputMappingSnakeCaseEncode() throws {
        let mapping = InputMapping(
            portId: "input",
            sourcePath: "nodeA.output",
            transform: "lowercase"
        )
        let data = try JSONEncoder().encode(mapping)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["port_id"] as? String, "input")
        XCTAssertEqual(json?["source_path"] as? String, "nodeA.output")
        XCTAssertEqual(json?["transform"] as? String, "lowercase")
    }

    func testInputMappingSnakeCaseDecode() throws {
        let data = """
        {
            "port_id": "in",
            "source_path": "a.b",
            "transform": null
        }
        """.data(using: .utf8)!
        let mapping = try JSONDecoder().decode(InputMapping.self, from: data)
        XCTAssertEqual(mapping.portId, "in")
        XCTAssertEqual(mapping.sourcePath, "a.b")
        XCTAssertNil(mapping.transform)
    }

    // MARK: - AgentType

    func testAgentTypeRawValuesStable() {
        // Source-of-truth strings shared with Python backend.
        XCTAssertEqual(AgentType.react.rawValue, "react")
        XCTAssertEqual(AgentType.toolCalling.rawValue, "tool_calling")
        XCTAssertEqual(AgentType.planAndExecute.rawValue, "plan_execute")
    }

    func testAgentTypeAllCasesCount() {
        XCTAssertEqual(AgentType.allCases.count, 3)
    }

    func testAgentTypeDisplayNames() {
        XCTAssertEqual(AgentType.react.displayName, "ReAct")
        XCTAssertEqual(AgentType.toolCalling.displayName, "Tool Calling")
        XCTAssertEqual(AgentType.planAndExecute.displayName, "Plan & Execute")
    }

    func testAgentTypeIcons() {
        // SF Symbols — drift breaks the agent-type picker.
        XCTAssertEqual(AgentType.react.icon, "brain")
        XCTAssertEqual(AgentType.toolCalling.icon, "wrench.and.screwdriver")
        XCTAssertEqual(AgentType.planAndExecute.icon, "list.bullet.clipboard")
    }

    func testAgentTypeDescriptionsNonEmpty() {
        for type in AgentType.allCases {
            XCTAssertFalse(type.description.isEmpty, "type=\(type)")
        }
    }
}
