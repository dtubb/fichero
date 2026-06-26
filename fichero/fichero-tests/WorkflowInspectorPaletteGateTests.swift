@testable import Fichero
import XCTest

@MainActor
final class WorkflowInspectorPaletteGateTests: XCTestCase {

    func testReleaseProfileKeepsBuiltinWorkflowCategoriesVisible() {
        let featureManager = FeatureManager.shared
        featureManager.resetToV001()

        XCTAssertTrue(WorkflowPaletteGate.isBuiltinCategoryEnabled("audio", featureManager: featureManager))
        XCTAssertTrue(WorkflowPaletteGate.isBuiltinCategoryEnabled("video", featureManager: featureManager))
        XCTAssertTrue(WorkflowPaletteGate.isBuiltinCategoryEnabled("transform", featureManager: featureManager))
        XCTAssertTrue(WorkflowPaletteGate.isBuiltinCategoryEnabled("convert", featureManager: featureManager))
        XCTAssertTrue(WorkflowPaletteGate.isBuiltinCategoryEnabled("logic", featureManager: featureManager))
        XCTAssertTrue(WorkflowPaletteGate.isBuiltinCategoryEnabled("sink", featureManager: featureManager))
    }

    func testReleaseProfileKeepsBuiltinWorkflowToolsVisible() {
        let featureManager = FeatureManager.shared
        featureManager.resetToV001()

        let filesTool = ToolInfo(
            name: "files",
            displayName: "Files",
            description: "",
            category: "sources",
            icon: "folder",
            color: "blue",
            inputPorts: [],
            outputPorts: [],
            usesLLM: false,
            supportsBatch: false,
            supportsStreaming: false,
            supportsStructuredOutput: false,
            sortOrder: 0
        )
        let searchTool = ToolInfo(
            name: "search",
            displayName: "Search",
            description: "",
            category: "sources",
            icon: "magnifyingglass",
            color: "green",
            inputPorts: [],
            outputPorts: [],
            usesLLM: false,
            supportsBatch: false,
            supportsStreaming: false,
            supportsStructuredOutput: false,
            sortOrder: 1
        )

        XCTAssertTrue(WorkflowPaletteGate.isBuiltinToolEnabled(filesTool, featureManager: featureManager))
        XCTAssertTrue(WorkflowPaletteGate.isBuiltinToolEnabled(searchTool, featureManager: featureManager))
    }

    func testMCPAndAgentCategoriesRemainSeparatelyGated() {
        let featureManager = FeatureManager.shared
        featureManager.resetToV001()

        XCTAssertFalse(WorkflowPaletteGate.isBuiltinCategoryEnabled("agent", featureManager: featureManager))
        XCTAssertFalse(WorkflowPaletteGate.isBuiltinCategoryEnabled("mcp", featureManager: featureManager))
        XCTAssertFalse(WorkflowPaletteGate.isBuiltinCategoryEnabled("mcp_local", featureManager: featureManager))
    }
}
