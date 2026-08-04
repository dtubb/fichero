import CoreGraphics
@testable import Fichero
import Foundation
import XCTest

/// Tests for ViewContexts — per-tab persisted UI state structs.
/// The high-value lock is WorkflowContext's hand-rolled Codable, which flattens
/// CGPoint into canvas_position_x/y; plus default values and Codable round-trips
/// for every context so persistence stays lossless.
final class ViewContextsTests: XCTestCase {

    // MARK: - Defaults

    func testLibraryContextDefaults() {
        let ctx = LibraryContext()
        XCTAssertNil(ctx.selectedCollectionId)
        XCTAssertTrue(ctx.selectedDocumentIds.isEmpty)
        XCTAssertTrue(ctx.showInspector)
    }

    func testWorkflowContextDefaults() {
        let ctx = WorkflowContext()
        XCTAssertNil(ctx.workflowId)
        XCTAssertEqual(ctx.canvasPosition, .zero)
        XCTAssertEqual(ctx.zoom, 1.0, accuracy: 1e-9)
        XCTAssertTrue(ctx.selectedNodeIds.isEmpty)
        XCTAssertTrue(ctx.showInspector)
    }

    func testSearchContextDefaults() {
        let ctx = SearchContext()
        XCTAssertEqual(ctx.query, "")
        XCTAssertNil(ctx.savedSearchId)
        XCTAssertNil(ctx.lastSearchQuery)
        XCTAssertTrue(ctx.showInspector)
    }

    // MARK: - WorkflowContext custom Codable (CGPoint flattening)

    func testWorkflowContextEncodesFlatPointKeys() throws {
        let ctx = WorkflowContext(
            workflowId: "wf-1",
            canvasPosition: CGPoint(x: 12.5, y: -7.0),
            zoom: 2.0,
            selectedNodeIds: ["n1"],
            showInspector: false
        )
        let data = try JSONEncoder().encode(ctx)
        let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        // The point must be flattened, not nested as a CGPoint object.
        XCTAssertEqual(object?["canvasPositionX"] as? Double, 12.5)
        XCTAssertEqual(object?["canvasPositionY"] as? Double, -7.0)
        XCTAssertNil(object?["canvasPosition"])
    }

    func testWorkflowContextDecodesFlatPointKeys() throws {
        let json = """
        {
            "workflowId": "wf-9",
            "canvasPositionX": 3.0,
            "canvasPositionY": 4.0,
            "zoom": 1.5,
            "selectedNodeIds": ["a", "b"],
            "showInspector": true
        }
        """
        let ctx = try JSONDecoder().decode(WorkflowContext.self, from: Data(json.utf8))
        XCTAssertEqual(ctx.workflowId, "wf-9")
        XCTAssertEqual(ctx.canvasPosition, CGPoint(x: 3.0, y: 4.0))
        XCTAssertEqual(ctx.zoom, 1.5, accuracy: 1e-9)
        XCTAssertEqual(ctx.selectedNodeIds, ["a", "b"])
    }

    func testWorkflowContextCodableRoundTripPreservesPoint() throws {
        let original = WorkflowContext(
            workflowId: "wf",
            canvasPosition: CGPoint(x: -1.25, y: 99.0),
            zoom: 0.5,
            selectedNodeIds: ["x"],
            showInspector: false
        )
        let restored = try JSONDecoder().decode(
            WorkflowContext.self,
            from: JSONEncoder().encode(original)
        )
        XCTAssertEqual(restored.canvasPosition, original.canvasPosition)
        XCTAssertEqual(restored.zoom, original.zoom, accuracy: 1e-9)
        XCTAssertEqual(restored.selectedNodeIds, original.selectedNodeIds)
        XCTAssertEqual(restored.showInspector, original.showInspector)
    }

    // MARK: - Other contexts round-trip

    func testChatContextRoundTrip() throws {
        let original = ChatContext(
            conversationId: "c-1",
            selectedDocuments: ["d1", "d2"],
            showInspector: false,
            selectedProvider: "anthropic",
            selectedModel: "claude"
        )
        let restored = try JSONDecoder().decode(
            ChatContext.self,
            from: JSONEncoder().encode(original)
        )
        XCTAssertEqual(restored.conversationId, "c-1")
        XCTAssertEqual(restored.selectedDocuments, ["d1", "d2"])
        XCTAssertEqual(restored.selectedProvider, "anthropic")
        XCTAssertEqual(restored.selectedModel, "claude")
        XCTAssertFalse(restored.showInspector)
    }
}
