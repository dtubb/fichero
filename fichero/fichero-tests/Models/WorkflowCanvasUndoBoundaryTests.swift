import XCTest

final class WorkflowCanvasUndoBoundaryTests: XCTestCase {
    func testWorkflowCanvasWiresUndoManagerForCanvasMutations() throws {
        let canvasSource = try Self.appSource("Views/Workflow/Canvas/WorkflowCanvasView.swift")
        XCTAssertTrue(canvasSource.contains("@Environment(\\.undoManager) var undoManager"))
        XCTAssertTrue(canvasSource.contains("registerUndo(from: previousWorkflow"))

        let gesturesSource = try Self.appSource("Views/Workflow/Canvas/WorkflowCanvasView+Gestures.swift")
        XCTAssertTrue(gesturesSource.contains("func finishNodeDrag()"))
        XCTAssertTrue(gesturesSource.contains("registerUndo(from: previousWorkflow, actionName: \"Move Node\")"))

        let edgeSource = try Self.appSource("Views/Workflow/Canvas/WorkflowCanvasView+EdgeConnection.swift")
        XCTAssertTrue(edgeSource.contains("registerUndo(from: previousWorkflow, actionName: \"Add Connection\")"))

        let dropSource = try Self.appSource("Views/Workflow/Canvas/WorkflowCanvasView+DropHandling.swift")
        XCTAssertTrue(dropSource.contains("registerUndo(from: previousWorkflow, actionName: \"Add Node\")"))
    }

    func testDuplicateNodePreservesEditableConfiguration() throws {
        let source = try Self.appSource("Views/Workflow/Canvas/WorkflowCanvasView+NodesLayer.swift")

        for property in [
            "description", "enabled", "inputMappings", "inputs", "config", "outputSchema", "usesLLM"
        ] {
            XCTAssertTrue(source.contains("\(property): original.\(property)"), property)
        }
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
