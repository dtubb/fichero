@testable import Fichero
import Foundation
import XCTest

/// Tests for EdgeFanRole + EdgeFanRoleResolver — the workflow-edge fan badge
/// logic. Since #4322 the resolver derives roles from registry metadata
/// (source-port cardinality + supports_batch), not tool-name allowlists:
/// zoom edges (the real 1→N step) get the badge, transcribe's outgoing
/// files no longer decorate spuriously as fan-out.
final class EdgeFanRoleTests: XCTestCase {

    // MARK: - EdgeFanRole.label

    func testFanOutLabel() {
        XCTAssertEqual(EdgeFanRole.fanOut.label(count: 3), "→ 3 files")
        XCTAssertEqual(EdgeFanRole.fanOut.label(count: nil), "fan-out")
    }

    func testFanInLabel() {
        XCTAssertEqual(EdgeFanRole.fanIn.label(count: 5), "∑ 5 files")
        XCTAssertEqual(EdgeFanRole.fanIn.label(count: nil), "merge")
    }

    func testNoneLabelIsEmptyRegardlessOfCount() {
        XCTAssertEqual(EdgeFanRole.none.label(count: 9), "")
        XCTAssertEqual(EdgeFanRole.none.label(count: nil), "")
    }

    // MARK: - EdgeFanRoleResolver.role (metadata-derived, #4322)

    func testPluralPayloadIntoBatchToolIsFanOut() {
        // files → transcribe: a files payload into a per-file batch tool.
        XCTAssertEqual(
            EdgeFanRoleResolver.role(
                sourcePortDataType: "files",
                sourceSupportsBatch: false,
                targetSupportsBatch: true
            ),
            .fanOut
        )
    }

    func testZoomStyleEdgeIsFanOut() {
        // zoom → transcribe: zoom emits N tiles (files) into a batch tool.
        XCTAssertEqual(
            EdgeFanRoleResolver.role(
                sourcePortDataType: "files",
                sourceSupportsBatch: true,
                targetSupportsBatch: true
            ),
            .fanOut
        )
    }

    func testBatchSourceWithSingularPayloadIsFanIn() {
        // transcribe → catalogue: per-file text results merge into one step.
        XCTAssertEqual(
            EdgeFanRoleResolver.role(
                sourcePortDataType: "text",
                sourceSupportsBatch: true,
                targetSupportsBatch: false
            ),
            .fanIn
        )
    }

    func testTranscribeOutgoingEdgeIsNotFanOut() {
        // The old allowlist decorated every transcribe→X edge as fan-out.
        // A singular text payload must never read as branching.
        XCTAssertNotEqual(
            EdgeFanRoleResolver.role(
                sourcePortDataType: "text",
                sourceSupportsBatch: true,
                targetSupportsBatch: true
            ),
            .fanOut
        )
    }

    func testPluralPayloadIntoNonBatchToolIsNone() {
        // files → catalogue: the list is ingested once, no parallel fan.
        XCTAssertEqual(
            EdgeFanRoleResolver.role(
                sourcePortDataType: "files",
                sourceSupportsBatch: false,
                targetSupportsBatch: false
            ),
            .none
        )
    }

    func testUnknownCardinalityIsNone() {
        XCTAssertEqual(
            EdgeFanRoleResolver.role(
                sourcePortDataType: nil,
                sourceSupportsBatch: true,
                targetSupportsBatch: true
            ),
            .none
        )
        XCTAssertEqual(
            EdgeFanRoleResolver.role(
                sourcePortDataType: "any",
                sourceSupportsBatch: true,
                targetSupportsBatch: true
            ),
            .none
        )
    }

    // MARK: - Source-port data-type resolution

    private func makeNode(outputPorts: [PortInfo]) -> WorkflowNode {
        WorkflowNode(id: "n-1", tool: "zoom", outputPorts: outputPorts)
    }

    private func makeEdge(sourcePort: String) -> WorkflowEdge {
        WorkflowEdge(sourceNodeId: "n-1", targetNodeId: "n-2", sourcePortId: sourcePort)
    }

    func testSourcePortDataTypeResolvesNamedPort() {
        let node = makeNode(outputPorts: [
            PortInfo(id: "files", name: "Files", portType: "output", dataType: "files"),
            PortInfo(id: "documents", name: "Documents", portType: "output", dataType: "json")
        ])
        XCTAssertEqual(
            EdgeFanRoleResolver.sourcePortDataType(edge: makeEdge(sourcePort: "documents"), sourceNode: node),
            "json"
        )
    }

    func testSourcePortDataTypeFallsBackToFirstPortForDefaultOutputId() {
        // Edges stored with the backend default port id "output" resolve to
        // the node's first output port, mirroring the geometry fallback.
        let node = makeNode(outputPorts: [
            PortInfo(id: "files", name: "Files", portType: "output", dataType: "files")
        ])
        XCTAssertEqual(
            EdgeFanRoleResolver.sourcePortDataType(edge: makeEdge(sourcePort: "output"), sourceNode: node),
            "files"
        )
    }

    func testSourcePortDataTypeUnknownPortIsNil() {
        let node = makeNode(outputPorts: [
            PortInfo(id: "files", name: "Files", portType: "output", dataType: "files")
        ])
        XCTAssertNil(
            EdgeFanRoleResolver.sourcePortDataType(edge: makeEdge(sourcePort: "mystery"), sourceNode: node)
        )
        XCTAssertNil(
            EdgeFanRoleResolver.sourcePortDataType(edge: makeEdge(sourcePort: "files"), sourceNode: nil)
        )
    }

    // MARK: - Registry-driven convenience overload

    private func toolInfo(name: String, supportsBatch: Bool) -> ToolInfo {
        ToolInfo(
            name: name, displayName: name, description: "", category: "transform",
            icon: "gearshape", color: "gray",
            inputPorts: [], outputPorts: [],
            usesLLM: false, supportsBatch: supportsBatch,
            supportsStreaming: false, supportsStructuredOutput: false, sortOrder: 1
        )
    }

    func testRegistryOverloadDerivesZoomFanOut() {
        let zoom = WorkflowNode(
            id: "z", tool: "zoom",
            outputPorts: [PortInfo(id: "files", name: "Files", portType: "output", dataType: "files")]
        )
        let transcribe = WorkflowNode(id: "t", tool: "transcribe")
        let edge = WorkflowEdge(sourceNodeId: "z", targetNodeId: "t", sourcePortId: "files")
        let registry = [
            "zoom": toolInfo(name: "zoom", supportsBatch: true),
            "transcribe": toolInfo(name: "transcribe", supportsBatch: true)
        ]
        XCTAssertEqual(
            EdgeFanRoleResolver.role(edge: edge, sourceNode: zoom, targetNode: transcribe, toolRegistry: registry),
            .fanOut
        )
    }

    func testRegistryOverloadUnknownToolsProduceNoBadge() {
        let source = WorkflowNode(
            id: "a", tool: "mystery",
            outputPorts: [PortInfo(id: "text", name: "Text", portType: "output", dataType: "text")]
        )
        let target = WorkflowNode(id: "b", tool: "unknown")
        let edge = WorkflowEdge(sourceNodeId: "a", targetNodeId: "b", sourcePortId: "text")
        XCTAssertEqual(
            EdgeFanRoleResolver.role(edge: edge, sourceNode: source, targetNode: target, toolRegistry: [:]),
            .none
        )
    }
}
