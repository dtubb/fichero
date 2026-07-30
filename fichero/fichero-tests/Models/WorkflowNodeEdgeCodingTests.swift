@testable import Fichero
import XCTest

/// Covers the WorkflowNode + WorkflowEdge custom Codable conformances.
/// WorkflowModelTests exercises WorkflowDefinition's decoder but not these two,
/// which apply defaults for missing fields and translate backend key names
/// (source/target/source_port) to the UI's field names. Pure decode/encode.
final class WorkflowNodeEdgeCodingTests: XCTestCase {

    func testServiceRestoresDefaultsForBothPortDirections() throws {
        let sourceURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero/Services/WorkflowService.swift")
        let source = try String(contentsOf: sourceURL, encoding: .utf8)

        XCTAssertEqual(
            source.components(separatedBy: "defaultValue: convertPortDefaultValue(port._default)").count - 1,
            3
        )
    }

    // MARK: - WorkflowNode decode defaults

    func testNodeMinimalDecodeAppliesDefaults() throws {
        let json = Data("""
        { "id": "n-1", "tool": "search" }
        """.utf8)
        let node = try JSONDecoder().decode(WorkflowNode.self, from: json)
        XCTAssertEqual(node.id, "n-1")
        XCTAssertEqual(node.tool, "search")
        XCTAssertNil(node.label)
        XCTAssertEqual(node.positionX, 0)
        XCTAssertEqual(node.positionY, 0)
        XCTAssertTrue(node.enabled)          // default true
        XCTAssertEqual(node.inputPorts, [])
        XCTAssertEqual(node.outputPorts, [])
        XCTAssertEqual(node.inputMappings, [])
        XCTAssertNil(node.inputs)
        XCTAssertNil(node.config)
        XCTAssertNil(node.outputSchema)
        XCTAssertFalse(node.usesLLM)         // default false
    }

    func testNodeDecodesSnakeCaseKeys() throws {
        let json = Data("""
        {
            "id": "n-2",
            "tool": "llm",
            "label": "Summarize",
            "position_x": 120.5,
            "position_y": 40.0,
            "enabled": false,
            "input_ports": [],
            "output_ports": [],
            "provider_name": "openai",
            "model_name": "gpt",
            "uses_llm": true
        }
        """.utf8)
        let node = try JSONDecoder().decode(WorkflowNode.self, from: json)
        XCTAssertEqual(node.label, "Summarize")
        XCTAssertEqual(node.positionX, 120.5)   // ← position_x
        XCTAssertEqual(node.positionY, 40.0)    // ← position_y
        XCTAssertFalse(node.enabled)
        XCTAssertEqual(node.providerName, "openai")  // ← provider_name
        XCTAssertEqual(node.modelName, "gpt")        // ← model_name
        XCTAssertTrue(node.usesLLM)                  // ← uses_llm
    }

    // MARK: - WorkflowEdge decode (backend keys + defaults)

    func testEdgeDecodesBackendKeys() throws {
        let json = Data("""
        {
            "id": "e-1",
            "source": "n-1",
            "target": "n-2",
            "source_port": "out",
            "target_port": "in",
            "animated": true,
            "route_key": "$.kind",
            "route_map": {"a": "n-3"}
        }
        """.utf8)
        let edge = try JSONDecoder().decode(WorkflowEdge.self, from: json)
        XCTAssertEqual(edge.sourceNodeId, "n-1")   // ← source
        XCTAssertEqual(edge.targetNodeId, "n-2")   // ← target
        XCTAssertEqual(edge.sourcePortId, "out")   // ← source_port
        XCTAssertEqual(edge.targetPortId, "in")    // ← target_port
        XCTAssertTrue(edge.animated)
        XCTAssertEqual(edge.routeKey, "$.kind")
        XCTAssertEqual(edge.routeMap, ["a": "n-3"])
    }

    // MARK: - WorkflowEdge strict decoding (#4322)
    //
    // The decoder used to silently default missing endpoints to "" and
    // missing ports to output/input, so malformed edges rendered as
    // plausible-looking connections. Missing keys must now throw. The
    // engine always serializes all four keys, so a miss is a real defect.

    /// A sparse edge (only id) is malformed — it must throw, not default.
    func testEdgeMissingEndpointsThrows() {
        let json = Data("""
        { "id": "e-2" }
        """.utf8)
        XCTAssertThrowsError(try JSONDecoder().decode(WorkflowEdge.self, from: json))
    }

    func testEdgeMissingSourcePortThrows() {
        let json = Data("""
        { "id": "e-2", "source": "n-1", "target": "n-2", "target_port": "in" }
        """.utf8)
        XCTAssertThrowsError(try JSONDecoder().decode(WorkflowEdge.self, from: json))
    }

    func testEdgeMissingTargetPortThrows() {
        let json = Data("""
        { "id": "e-2", "source": "n-1", "target": "n-2", "source_port": "out" }
        """.utf8)
        XCTAssertThrowsError(try JSONDecoder().decode(WorkflowEdge.self, from: json))
    }

    /// Optional decoration stays optional: only ids/endpoints/ports are strict.
    func testEdgeOptionalFieldsStillDefault() throws {
        let json = Data("""
        { "id": "e-2", "source": "n-1", "target": "n-2",
          "source_port": "out", "target_port": "in" }
        """.utf8)
        let edge = try JSONDecoder().decode(WorkflowEdge.self, from: json)
        XCTAssertFalse(edge.animated)
        XCTAssertNil(edge.condition)
        XCTAssertNil(edge.label)
        XCTAssertNil(edge.routeKey)
        XCTAssertNil(edge.routeMap)
    }

    /// Route-map edges fan to multiple targets; the engine serializes their
    /// `target` as "" — the KEY must exist, the value may be empty.
    func testEdgeEmptyTargetValueAllowedForRouteMapEdges() throws {
        let json = Data("""
        { "id": "e-2", "source": "n-1", "target": "",
          "source_port": "out", "target_port": "in",
          "route_key": "$.kind", "route_map": {"a": "n-3"} }
        """.utf8)
        let edge = try JSONDecoder().decode(WorkflowEdge.self, from: json)
        XCTAssertEqual(edge.targetNodeId, "")
        XCTAssertEqual(edge.routeMap, ["a": "n-3"])
    }

    // MARK: - WorkflowEdge encode always writes backend format

    func testEdgeEncodesBackendKeyNames() throws {
        let edge = WorkflowEdge(id: "e-3", sourceNodeId: "s", targetNodeId: "t",
                                sourcePortId: "op", targetPortId: "ip")
        let data = try JSONEncoder().encode(edge)
        let obj = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(obj["source"] as? String, "s")
        XCTAssertEqual(obj["target"] as? String, "t")
        XCTAssertEqual(obj["source_port"] as? String, "op")
        XCTAssertEqual(obj["target_port"] as? String, "ip")
        // UI field names must never leak to the wire.
        XCTAssertNil(obj["sourceNodeId"])
        XCTAssertNil(obj["targetNodeId"])
    }

    /// Encode→decode preserves the edge because both speak backend format.
    func testEdgeRoundTripThroughBackendFormat() throws {
        let original = WorkflowEdge(id: "e-4", sourceNodeId: "s", targetNodeId: "t",
                                    sourcePortId: "op", targetPortId: "ip",
                                    condition: "x>1", label: "L", animated: true,
                                    routeKey: "$.k", routeMap: ["y": "n-9"])
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(WorkflowEdge.self, from: data)
        XCTAssertEqual(decoded, original)
    }
}
