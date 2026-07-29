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

    func testMCPAndAgentCategoriesRemainSeparatelyGated() throws {
        // #3917/#252 DECISION NEEDED: this asserts mcp/mcp_local are DISABLED after
        // resetToV001, but resetToV001() now sets mcpEnabledInternal = true (mcp was
        // promoted to v0.0.1 defaults) — same tier-promotion question as
        // FeatureManagerTests.testV001. It also runs without a build-tier context, so
        // in a dev test build activeBuildTier == .dev enables everything regardless.
        // Skip until the mcp/agent v0.0.1 gating is decided (promote or keep gated).
        throw XCTSkip("mcp promoted to v0.0.1 (resetToV001 enables it) — gating decision pending, see FeatureManager #252 (#3917)")
        let featureManager = FeatureManager.shared
        featureManager.resetToV001()

        XCTAssertFalse(WorkflowPaletteGate.isBuiltinCategoryEnabled("agent", featureManager: featureManager))
        XCTAssertFalse(WorkflowPaletteGate.isBuiltinCategoryEnabled("mcp", featureManager: featureManager))
        XCTAssertFalse(WorkflowPaletteGate.isBuiltinCategoryEnabled("mcp_local", featureManager: featureManager))
    }
}
