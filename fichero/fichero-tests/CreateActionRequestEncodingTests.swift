@testable import Fichero
import XCTest

/// Tests for CreateActionRequest.encode. The custom encoder declares CodingKeys
/// for node_template/nodes/edges but historically omitted them — a silent
/// write-drop if a caller ever populated a node graph. This pins both the
/// preserved current behavior (empty → omitted) and the fix (populated →
/// round-trips through AnyCodable). Pure encode, no live engine.
final class CreateActionRequestEncodingTests: XCTestCase {

    private func encodeToDict(_ req: CreateActionRequest) throws -> [String: Any] {
        let data = try JSONEncoder().encode(req)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    /// The scalar fields always encode; empty graph fields stay omitted so the
    /// current caller's wire form is unchanged.
    func testEncodesScalarsAndOmitsEmptyGraphFields() throws {
        var req = CreateActionRequest(name: "My Action")
        req.description = "does things"
        req.category = "custom"
        req.tags = ["a", "b"]
        let obj = try encodeToDict(req)
        XCTAssertEqual(obj["name"] as? String, "My Action")
        XCTAssertEqual(obj["description"] as? String, "does things")
        XCTAssertEqual(obj["tags"] as? [String], ["a", "b"])
        XCTAssertEqual(obj["icon"] as? String, "square.stack.3d.up")  // default
        // Empty graph fields are omitted (not sent as empty {} / []).
        XCTAssertNil(obj["node_template"])
        XCTAssertNil(obj["nodes"])
        XCTAssertNil(obj["edges"])
    }

    /// A populated node graph must round-trip on the wire instead of being
    /// silently dropped.
    func testEncodesPopulatedGraphFields() throws {
        var req = CreateActionRequest(name: "Graph Action")
        req.nodeTemplate = ["kind": "prototype", "version": 2]
        req.nodes = [["id": "n1", "tool": "search"], ["id": "n2", "tool": "summarize"]]
        req.edges = [["source": "n1", "target": "n2"]]
        let obj = try encodeToDict(req)

        let template = try XCTUnwrap(obj["node_template"] as? [String: Any])  // ← snake_case
        XCTAssertEqual(template["kind"] as? String, "prototype")
        XCTAssertEqual(template["version"] as? Int, 2)

        let nodes = try XCTUnwrap(obj["nodes"] as? [[String: Any]])
        XCTAssertEqual(nodes.count, 2)
        XCTAssertEqual(nodes[0]["tool"] as? String, "search")
        XCTAssertEqual(nodes[1]["id"] as? String, "n2")

        let edges = try XCTUnwrap(obj["edges"] as? [[String: Any]])
        XCTAssertEqual(edges.count, 1)
        XCTAssertEqual(edges[0]["source"] as? String, "n1")
        XCTAssertEqual(edges[0]["target"] as? String, "n2")
    }
}
