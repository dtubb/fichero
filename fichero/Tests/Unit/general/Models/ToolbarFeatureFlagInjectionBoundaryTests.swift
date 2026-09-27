import XCTest

final class ToolbarFeatureFlagInjectionBoundaryTests: XCTestCase {
    func testToolbarLeavesDoNotReadFeatureManagerSharedDirectly() throws {
        let workflowToolbar = try Self.appSource("Views/Workflow/WorkflowToolbar.swift")
        XCTAssertFalse(workflowToolbar.contains("FeatureManager.shared"))
        XCTAssertTrue(workflowToolbar.contains("let showImportExport: Bool"))
        XCTAssertTrue(workflowToolbar.contains("let showLangGraphPreview: Bool"))
        XCTAssertTrue(workflowToolbar.contains("let showFilesToolbarButton: Bool"))

        // MiniToolbarComponents.swift was deleted 2026-09-27 (#2955): all four of its
        // components were unreferenced, superseded by the generic `MiniToolbar`. The
        // boundary it half-guarded is still asserted above on `WorkflowToolbar`, the
        // live toolbar leaf that takes injected flags.
    }

    func testWorkflowEditorReadsFeatureManagerFromEnvironment() throws {
        let source = try Self.appSource("Views/Workflow/Editor/WorkflowEditor.swift")
        XCTAssertTrue(source.contains("@Environment(FeatureManager.self) var featureManager"))
        XCTAssertFalse(source.contains("@ObservedObject var featureManager = FeatureManager.shared"))
        XCTAssertTrue(source.contains("showImportExport: featureManager.isWorkflowImportExportEnabled"))
    }

    func testWorkflowNodeSurfacesReadFeatureManagerFromEnvironment() throws {
        // Per-port geometry + data-type icons ship un-gated (#4322): the node
        // view and port-position math must not consult the feature flag (or
        // the singleton) any more.
        let nodeView = try Self.appSource("Views/Workflow/Nodes/WorkflowNodeView.swift")
        XCTAssertFalse(nodeView.contains("FeatureManager.shared"))
        XCTAssertFalse(nodeView.contains("isWorkflowEditorAdvancedViewsEnabled"))
        XCTAssertTrue(nodeView.contains("showPortDetails: true"))

        let nodePopover = try Self.appSource("Views/Workflow/Nodes/NodePopover.swift")
        XCTAssertTrue(nodePopover.contains("@Environment(FeatureManager.self) private var featureManager"))
        XCTAssertFalse(nodePopover.contains("@ObservedObject var featureManager = FeatureManager.shared"))

        let edgeConnections = try Self.appSource("Views/Workflow/Canvas/WorkflowCanvasView+EdgeConnection.swift")
        XCTAssertFalse(edgeConnections.contains("isWorkflowEditorAdvancedViewsEnabled"))
        XCTAssertFalse(edgeConnections.contains("FeatureManager.shared"))
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = try AppSource.root()
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
