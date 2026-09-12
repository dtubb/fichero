@testable import Fichero
import Foundation
import XCTest

final class NodeProviderModelSelectorVisionModeTests: XCTestCase {

    func testAllRuntimeModelAliasesAreRecognized() {
        for providerId in ["$small", "$large", "$vision_small", "$vision_medium", "$vision_large"] {
            XCTAssertTrue(isModelAliasProviderId(providerId), providerId)
        }
        XCTAssertFalse(isModelAliasProviderId("openai"))
    }

    func testConfiguredProviderPrefersTypedFieldAndReadsLegacyConfig() {
        var node = WorkflowNode(
            tool: "transcribe",
            config: ["provider_name": .string("$vision_small")]
        )
        XCTAssertEqual(configuredNodeProviderId(node), "$vision_small")

        node.providerName = "$vision_large"
        XCTAssertEqual(configuredNodeProviderId(node), "$vision_large")
    }

    // Spec: docs/contributor/specs/ui/workflow-node-config.md
    // `nodeconfig.model.uses-llm-is-tool-fact` — usesLLM describes the TOOL and
    // never changes with the provider choice. Choosing "Default" used to set it
    // false, after which the provider section, Compare Models and the Prompt
    // Preview were hidden on reopen for every non-vision LLM tool.

    private static let providers: [ModelPicker.ProviderOption] = [
        .init(id: "prov-openai", name: "OpenAI", providerType: "openai", available: true, supportsVision: true,
              models: [.init(id: "gpt-4o", name: "GPT-4o"), .init(id: "gpt-4o-mini", name: "GPT-4o mini")])
    ]

    func testChoosingDefaultKeepsUsesLLMAndClearsSelection() {
        var node = WorkflowNode(
            tool: "summarize_file",
            config: ["style": .string("brief"), "vision_mode": .string("llm")],
            providerName: "prov-openai",
            modelName: "gpt-4o",
            usesLLM: true
        )
        let model = NodeProviderModelSelector.apply(
            providerId: "", to: &node, providers: Self.providers, currentModelId: "gpt-4o"
        )
        XCTAssertTrue(node.usesLLM, "a tool fact, not a selection fact")
        XCTAssertNil(node.providerName)
        XCTAssertNil(node.modelName)
        XCTAssertNil(node.config?["vision_mode"])
        XCTAssertNil(node.config?["provider_name"])
        XCTAssertEqual(node.config?["style"], .string("brief"), "unrelated config untouched")
        XCTAssertEqual(model, "")
    }

    func testChoosingAliasAndProviderMapOntoNode() {
        var node = WorkflowNode(tool: "summarize_file", usesLLM: true)

        var model = NodeProviderModelSelector.apply(
            providerId: "$large", to: &node, providers: Self.providers, currentModelId: ""
        )
        XCTAssertEqual(node.providerName, "$large")
        XCTAssertNil(node.modelName)
        XCTAssertTrue(node.usesLLM)
        XCTAssertEqual(model, "")

        model = NodeProviderModelSelector.apply(
            providerId: "prov-openai", to: &node, providers: Self.providers, currentModelId: ""
        )
        XCTAssertEqual(node.providerName, "prov-openai")
        XCTAssertEqual(node.modelName, "gpt-4o", "first configured model auto-selected")
        XCTAssertEqual(node.config?["vision_mode"], .string("llm"))
        XCTAssertTrue(node.usesLLM)
        XCTAssertEqual(model, "gpt-4o")
    }

    func testAppleVisionSelectionSetsAppleMode() {
        var node = WorkflowNode(tool: "transcribe", providerName: "prov-openai", modelName: "gpt-4o", usesLLM: true)
        _ = NodeProviderModelSelector.apply(
            providerId: appleVisionProviderId, to: &node, providers: Self.providers, currentModelId: "gpt-4o"
        )
        XCTAssertEqual(node.config?["vision_mode"], .string("apple"))
        XCTAssertNil(node.providerName)
        XCTAssertNil(node.modelName)
    }

    private static func source() throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent("Views/Workflow/Nodes/NodeProviderModelSelector.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testLeavingAppleVisionClearsVisionModeForDefaultAndAliases() throws {
        let source = try Self.source()
        let clear = "node.config?.removeValue(forKey: \"vision_mode\")"
        let defaultRange = try XCTUnwrap(source.range(of: "if newValue.isEmpty"))
        let defaultExit = try XCTUnwrap(source.range(of: "return", range: defaultRange.lowerBound..<source.endIndex))
        let aliasRange = try XCTUnwrap(source.range(of: "isModelAliasProviderId(newValue)"))
        let llmRange = try XCTUnwrap(source.range(of: "// LLM provider selected"))

        XCTAssertNotNil(source.range(of: clear, range: defaultRange.lowerBound..<defaultExit.upperBound))
        XCTAssertNotNil(source.range(of: clear, range: aliasRange.lowerBound..<llmRange.lowerBound))
        XCTAssertTrue(source.contains("node.config?.removeValue(forKey: \"provider_name\")"))
    }
}
