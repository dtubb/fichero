import XCTest

final class WorkflowCanvasUndoBoundaryTests: XCTestCase {
    func testWorkflowCanvasWiresUndoManagerForCanvasMutations() throws {
        let canvasSource = try Self.appSource("Views/Workflow/WorkflowCanvasView.swift")
        XCTAssertTrue(canvasSource.contains("@Environment(\\.undoManager) private var undoManager"))
        XCTAssertTrue(canvasSource.contains("registerUndo(from: previousWorkflow"))

        let gesturesSource = try Self.appSource("Views/Workflow/WorkflowCanvasView+Gestures.swift")
        XCTAssertTrue(gesturesSource.contains("func finishNodeDrag()"))
        XCTAssertTrue(gesturesSource.contains("registerUndo(from: previousWorkflow, actionName: \"Move Node\")"))

        let edgeSource = try Self.appSource("Views/Workflow/WorkflowCanvasView+EdgeConnection.swift")
        XCTAssertTrue(edgeSource.contains("registerUndo(from: previousWorkflow, actionName: \"Add Connection\")"))

        let dropSource = try Self.appSource("Views/Workflow/WorkflowCanvasView+DropHandling.swift")
        XCTAssertTrue(dropSource.contains("registerUndo(from: previousWorkflow, actionName: \"Add Node\")"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
