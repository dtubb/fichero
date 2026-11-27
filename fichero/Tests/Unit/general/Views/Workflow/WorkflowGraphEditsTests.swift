@testable import Fichero
import XCTest

/// Canvas edits keep a node's input mappings in step with its edges.
///
/// The engine wires a node from its input mappings when it has any, and from
/// its incoming edges only when it has none (`workflows/builder.py`, the
/// auto-wire branch). An edge removed without its mapping therefore still
/// feeds the node at run, and stops the node's other edges from being wired.
/// spec: workflows `workflows.canvas.edit-keeps-mappings-with-edges`,
/// `workflows.canvas.one-edge-per-port-pair`,
/// `workflows.canvas.node-popover-follows-its-node`.
final class WorkflowGraphEditsTests: XCTestCase {

    private func node(_ id: String, mappings: [InputMapping] = []) -> WorkflowNode {
        WorkflowNode(id: id, tool: "transcribe", inputMappings: mappings)
    }

    private func mapping(_ port: String, from source: String, _ sourcePort: String) -> InputMapping {
        InputMapping(portId: port, sourcePath: "$.nodes.\(source).\(sourcePort)")
    }

    private func edge(
        _ id: String, _ source: String, _ sourcePort: String, _ target: String, _ targetPort: String
    ) -> WorkflowEdge {
        WorkflowEdge(
            id: id, sourceNodeId: source, targetNodeId: target,
            sourcePortId: sourcePort, targetPortId: targetPort
        )
    }

    // MARK: - Connecting

    func testConnectAddsTheEdgeAndItsMapping() {
        var workflow = Workflow(name: "w", nodes: [node("a"), node("b")])

        let added = workflow.connect(
            sourceNodeId: "a", sourcePortId: "text", targetNodeId: "b", targetPortId: "files"
        )

        XCTAssertTrue(added)
        XCTAssertEqual(workflow.edges.count, 1)
        XCTAssertEqual(workflow.node(withId: "b")?.inputMappings, [mapping("files", from: "a", "text")])
    }

    func testConnectingTheSamePortsTwiceAddsOneEdge() {
        var workflow = Workflow(name: "w", nodes: [node("a"), node("b")])
        workflow.connect(sourceNodeId: "a", sourcePortId: "text", targetNodeId: "b", targetPortId: "files")

        let addedAgain = workflow.connect(
            sourceNodeId: "a", sourcePortId: "text", targetNodeId: "b", targetPortId: "files"
        )

        XCTAssertFalse(addedAgain)
        XCTAssertEqual(workflow.edges.count, 1)
    }

    func testConnectRefusesANodeThatIsGone() {
        var workflow = Workflow(name: "w", nodes: [node("b")])

        let added = workflow.connect(
            sourceNodeId: "gone", sourcePortId: "text", targetNodeId: "b", targetPortId: "files"
        )

        XCTAssertFalse(added)
        XCTAssertTrue(workflow.edges.isEmpty)
        XCTAssertEqual(workflow.node(withId: "b")?.inputMappings, [])
    }

    // MARK: - Removing an edge

    func testRemovingAnEdgeRemovesTheMappingItMade() {
        var workflow = Workflow(
            name: "w",
            nodes: [node("a"), node("b", mappings: [mapping("files", from: "a", "text")])],
            edges: [edge("e1", "a", "text", "b", "files")]
        )

        workflow.removeEdge(id: "e1")

        XCTAssertTrue(workflow.edges.isEmpty)
        XCTAssertEqual(workflow.node(withId: "b")?.inputMappings, [])
    }

    func testRemovingAnEdgeKeepsAMappingThatReadsAnotherSource() {
        // The mapping on `files` was typed by hand to read node c; the edge
        // from a is not what it describes, so removing that edge leaves it.
        let typed = mapping("files", from: "c", "text")
        var workflow = Workflow(
            name: "w",
            nodes: [node("a"), node("c"), node("b", mappings: [typed])],
            edges: [edge("e1", "a", "text", "b", "files")]
        )

        workflow.removeEdge(id: "e1")

        XCTAssertEqual(workflow.node(withId: "b")?.inputMappings, [typed])
    }

    func testRemovingOneOfTwoEdgesIntoAPortPointsTheMappingAtTheOther() {
        var workflow = Workflow(
            name: "w",
            nodes: [node("a"), node("c"), node("b", mappings: [mapping("files", from: "c", "text")])],
            edges: [edge("e1", "a", "text", "b", "files"), edge("e2", "c", "text", "b", "files")]
        )

        workflow.removeEdge(id: "e2")

        XCTAssertEqual(workflow.edges.map(\.id), ["e1"])
        XCTAssertEqual(workflow.node(withId: "b")?.inputMappings, [mapping("files", from: "a", "text")])
    }

    // MARK: - Removing nodes

    func testRemovingANodeRemovesItsEdgesAndTheMappingsThatReadIt() {
        var workflow = Workflow(
            name: "w",
            nodes: [
                node("a"),
                node("b", mappings: [mapping("files", from: "a", "text")]),
                // No edge drawn: a mapping left by Duplicate, reading node a.
                node("c", mappings: [mapping("files", from: "a", "text"), mapping("extra", from: "b", "text")])
            ],
            edges: [edge("e1", "a", "text", "b", "files")]
        )

        workflow.removeNodes(ids: ["a"])

        XCTAssertEqual(workflow.nodes.map(\.id), ["b", "c"])
        XCTAssertTrue(workflow.edges.isEmpty)
        XCTAssertEqual(workflow.node(withId: "b")?.inputMappings, [])
        XCTAssertEqual(workflow.node(withId: "c")?.inputMappings, [mapping("extra", from: "b", "text")])
    }

    // MARK: - The node popover's binding

    func testReplacingANodeWritesItByIdNotByPosition() {
        var workflow = Workflow(name: "w", nodes: [node("a"), node("b")])
        var edited = node("b")
        edited.label = "Edited"

        workflow.removeNodes(ids: ["a"])   // b moves from index 1 to index 0
        workflow.replaceNode(edited)

        XCTAssertEqual(workflow.node(withId: "b")?.label, "Edited")
    }

    func testReplacingADeletedNodeChangesNothing() {
        var workflow = Workflow(name: "w", nodes: [node("a"), node("b")])
        var edited = node("b")
        edited.label = "Edited"

        workflow.removeNodes(ids: ["b"])
        let before = workflow
        workflow.replaceNode(edited)

        XCTAssertEqual(workflow, before)
        XCTAssertNil(workflow.node(withId: "b"))
    }
}
