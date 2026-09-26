@testable import Fichero
import XCTest

/// spec: workflow-node-config — the canvas node subtitle (F9b) and the Compare-Models Apply
/// updating the picker (F13). Both were client-side regressions the CD's node work surfaced.
final class NodeSubtitleAndApplyTests: XCTestCase {

    // MARK: F9b — canvas subtitle never blanks on an alias / Apple selection

    func testAppleVisionSubtitle() {
        XCTAssertEqual(
            WorkflowNodeView.nodeSubtitle(modelName: nil, providerName: "apple", visionMode: "apple"),
            "Apple Vision"
        )
    }

    func testConcreteModelWins() {
        XCTAssertEqual(
            WorkflowNodeView.nodeSubtitle(modelName: "gpt-4o", providerName: "openai", visionMode: nil),
            "gpt-4o"
        )
    }

    func testAliasRendersReadablyNotBlank() {
        // The bug: an alias selection ($vision_large / $large) carried no concrete modelName, so the
        // subtitle was nil (a blank node). It must now read the alias back.
        XCTAssertEqual(
            WorkflowNodeView.nodeSubtitle(modelName: nil, providerName: "$vision_large", visionMode: nil),
            "Vision · Large"
        )
        XCTAssertEqual(
            WorkflowNodeView.nodeSubtitle(modelName: nil, providerName: "$large", visionMode: nil),
            "Large"
        )
        // An empty modelName counts as "no model", so it still falls through to the alias.
        XCTAssertEqual(
            WorkflowNodeView.nodeSubtitle(modelName: "", providerName: "$small", visionMode: nil),
            "Small"
        )
    }

    func testPlainDefaultHasNoSubtitle() {
        // A plain provider with no model (the "Default" case) legitimately shows nothing.
        XCTAssertNil(
            WorkflowNodeView.nodeSubtitle(modelName: nil, providerName: "openai", visionMode: nil)
        )
        XCTAssertNil(
            WorkflowNodeView.nodeSubtitle(modelName: nil, providerName: nil, visionMode: nil)
        )
    }

    // MARK: F13 — applying a Compare-Models result moves the picker's own selection

    func testCompareApplyUpdatesNodeAndReturnsThePickerSelection() {
        var node = WorkflowNode(tool: "describe", providerName: "prov-old", modelName: "old-model", usesLLM: false)
        let selection = node.applyComparisonChoice(provider: "prov-new", model: "new-model")
        XCTAssertEqual(node.providerName, "prov-new")
        XCTAssertEqual(node.modelName, "new-model")
        XCTAssertTrue(node.usesLLM)
        // The picker's own selection moves with the node, or the chip shows the OLD model.
        XCTAssertEqual(selection.providerId, "prov-new")
        XCTAssertEqual(selection.modelId, "new-model")
    }

    // MARK: F5/entities — the Extract-Entities node exposes the shared prompt editor

    func testEntitiesNodeComposesPromptEditor() throws {
        // The server honors a `prompt` override for extract_entities, but the node had no editor.
        // It now composes the same NodePromptEditor as Describe/SummarizeFile (spec F5/entities).
        let url = try AppSource.root()
            .appendingPathComponent("Views/Workflow/Nodes/NodeConfigs/ExtractEntitiesNodeConfig.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(source.contains("NodePromptEditor"),
                      "entities node must compose the shared prompt editor")
        XCTAssertTrue(source.contains("backendPrompt"),
                      "entities node must thread the backend prompt so the ghost shows the effective prompt")
    }
}
