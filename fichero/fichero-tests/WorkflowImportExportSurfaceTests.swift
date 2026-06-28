import XCTest

final class WorkflowImportExportSurfaceTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testWorkflowEditorToolbarWiresImportAndExport() throws {
        let editor = try Self.appSource("Views/Workflow/WorkflowEditor.swift")
        let toolbar = try Self.appSource("Views/Toolbars/WorkflowToolbar.swift")

        XCTAssertTrue(editor.contains("onImport: importWorkflow"))
        XCTAssertTrue(editor.contains("onExport: exportWorkflow"))
        XCTAssertTrue(toolbar.contains("let onImport: () -> Void"))
        XCTAssertTrue(toolbar.contains("square.and.arrow.down"))
        XCTAssertTrue(toolbar.contains("square.and.arrow.up"))
    }

    func testWorkflowEditorToolbarUsesBottomMiniToolbarWithOverflow() throws {
        let editor = try Self.appSource("Views/Workflow/WorkflowEditor.swift")
        let toolbar = try Self.appSource("Views/Toolbars/WorkflowToolbar.swift")
        let canvasFrame = try XCTUnwrap(editor.range(of: ".frame(maxWidth: .infinity, maxHeight: .infinity)"))
        let toolbarPlacement = try XCTUnwrap(editor.range(of: "WorkflowToolbar(", range: canvasFrame.upperBound..<editor.endIndex))

        XCTAssertFalse(toolbarPlacement.isEmpty)
        XCTAssertTrue(toolbar.contains("MiniToolbar {"))
        XCTAssertTrue(toolbar.contains("ViewThatFits(in: .horizontal)"))
        XCTAssertTrue(toolbar.contains("ellipsis.circle"))
        XCTAssertFalse(toolbar.contains("Color(.controlBackgroundColor)"))
    }

    func testWorkflowImporterFailsLoudlyForBadFileShape() throws {
        let exporter = try Self.appSource("Models/WorkflowExporter.swift")

        XCTAssertTrue(exporter.contains("static func importFromFile"))
        XCTAssertTrue(exporter.contains("async throws -> String?"))
        XCTAssertTrue(exporter.contains("case invalidTopLevelObject"))
        XCTAssertFalse(exporter.contains("return nil\n        }\n\n            // Convert to AnyCodable"))
    }
}
