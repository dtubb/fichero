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

    func testCompareApplyUpdatesPickerSelection() throws {
        // The apply closure writes the node fields AND the picker's @State bindings, or the chip
        // shows the OLD model until the popover is reopened (the reported "Apply did nothing").
        let url = try AppSource.root()
            .appendingPathComponent("Views/Workflow/Nodes/NodePopover+Comparison.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(source.contains("selectedProviderId = provider"),
                      "Compare apply must move the provider selection so the chip updates")
        XCTAssertTrue(source.contains("selectedModelId = model"),
                      "Compare apply must move the model selection so the chip updates")
    }
}
