import XCTest

final class ToolbarFeatureFlagInjectionBoundaryTests: XCTestCase {
    func testToolbarLeavesDoNotReadFeatureManagerSharedDirectly() throws {
        let workflowToolbar = try Self.appSource("Views/Workflow/WorkflowToolbar.swift")
        XCTAssertFalse(workflowToolbar.contains("FeatureManager.shared"))
        XCTAssertTrue(workflowToolbar.contains("let showImportExport: Bool"))
        XCTAssertTrue(workflowToolbar.contains("let showLangGraphPreview: Bool"))
        XCTAssertTrue(workflowToolbar.contains("let showFilesToolbarButton: Bool"))

        let miniToolbar = try Self.appSource("Views/Components/MiniToolbarComponents.swift")
        XCTAssertFalse(miniToolbar.contains("FeatureManager.shared.isWorkflowRunOnSelectionEnabled"))
        XCTAssertTrue(miniToolbar.contains("let showRunOnSelection: Bool"))
    }

    func testWorkflowEditorReadsFeatureManagerFromEnvironment() throws {
        let source = try Self.appSource("Views/Workflow/Editor/WorkflowEditor.swift")
        XCTAssertTrue(source.contains("@EnvironmentObject var featureManager: FeatureManager"))
        XCTAssertFalse(source.contains("@ObservedObject var featureManager = FeatureManager.shared"))
        XCTAssertTrue(source.contains("showImportExport: featureManager.isWorkflowImportExportEnabled"))
    }

    func testWorkflowNodeSurfacesReadFeatureManagerFromEnvironment() throws {
        let nodeView = try Self.appSource("Views/Workflow/Nodes/WorkflowNodeView.swift")
        XCTAssertTrue(nodeView.contains("@EnvironmentObject private var featureManager: FeatureManager"))
        XCTAssertFalse(nodeView.contains("FeatureManager.shared"))

        let nodePopover = try Self.appSource("Views/Workflow/Nodes/NodePopover.swift")
        XCTAssertTrue(nodePopover.contains("@EnvironmentObject private var featureManager: FeatureManager"))
        XCTAssertFalse(nodePopover.contains("@ObservedObject var featureManager = FeatureManager.shared"))

        let edgeConnections = try Self.appSource("Views/Workflow/Canvas/WorkflowCanvasView+EdgeConnection.swift")
        XCTAssertTrue(edgeConnections.contains("let showAdvancedPorts = featureManager.isWorkflowEditorAdvancedViewsEnabled"))
        XCTAssertFalse(edgeConnections.contains("FeatureManager.shared.isWorkflowEditorAdvancedViewsEnabled"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
