@testable import Fichero
import Foundation
import XCTest

/// #4187 — the Run Workflow model submenu must filter to vision-capable
/// models for workflows with vision nodes, reading the SERVER-resolved
/// per-model capability. The engine's rule is tri-state: a model with no
/// saved capabilities inherits the provider's vision support — so a model
/// absent from `model_details` must fall back to the provider bool, never
/// be treated as text-only.
final class LLMProviderVisionFilterTests: XCTestCase {

    private func provider(
        models: [String] = [],
        supportsVision: Bool = false,
        details: [LLMProviderModelDetail] = []
    ) -> LLMProvider {
        LLMProvider(
            id: "p", name: "P", models: models, available: true,
            supportsVision: supportsVision, modelDetails: details
        )
    }

    // MARK: - Decoding

    func testDecodesModelDetails() throws {
        let json = Data("""
        {"id":"openrouter","name":"OpenRouter","models":["gpt-4o","text-only"],
         "available":true,"supports_vision":true,
         "model_details":[
            {"model_id":"gpt-4o","capabilities":["vision"],"supports_vision":true},
            {"model_id":"text-only","capabilities":["text"],"supports_vision":false}]}
        """.utf8)
        let decoded = try JSONDecoder().decode(LLMProvider.self, from: json)
        XCTAssertEqual(decoded.modelDetails.count, 2)
        XCTAssertTrue(decoded.supportsVision(model: "gpt-4o"))
        XCTAssertFalse(decoded.supportsVision(model: "text-only"))
    }

    func testDecodesPayloadWithoutModelDetails() throws {
        // Pre-#4187 payload shape must keep decoding, with provider fallback.
        let json = Data("""
        {"id":"apple","name":"Apple","models":["apple-intelligence"],
         "available":true,"supports_vision":true}
        """.utf8)
        let decoded = try JSONDecoder().decode(LLMProvider.self, from: json)
        XCTAssertTrue(decoded.modelDetails.isEmpty)
        XCTAssertTrue(decoded.supportsVision(model: "apple-intelligence"))
    }

    // MARK: - Per-model fallback (tri-state, resolved server-side)

    func testModelAbsentFromDetailsInheritsProviderCapability() {
        let visionProvider = provider(models: ["m"], supportsVision: true)
        XCTAssertTrue(visionProvider.supportsVision(model: "m"))

        let textProvider = provider(models: ["m"], supportsVision: false)
        XCTAssertFalse(textProvider.supportsVision(model: "m"))
    }

    func testExplicitDetailOverridesProviderCapability() {
        let sut = provider(
            models: ["text-only"],
            supportsVision: true,
            details: [.init(modelId: "text-only", supportsVision: false)]
        )
        XCTAssertFalse(sut.supportsVision(model: "text-only"))
    }

    // MARK: - Menu entry shape

    func testNonVisionWorkflowShowsAllModels() {
        let sut = provider(
            models: ["a", "b"],
            supportsVision: true,
            details: [.init(modelId: "a", supportsVision: false)]
        )
        XCTAssertEqual(sut.runMenuEntry(requiresVision: false), .models(["a", "b"]))
    }

    func testVisionWorkflowFiltersToVisionModels() {
        let sut = provider(
            models: ["gpt-4o", "text-only"],
            supportsVision: true,
            details: [
                .init(modelId: "gpt-4o", supportsVision: true),
                .init(modelId: "text-only", supportsVision: false)
            ]
        )
        XCTAssertEqual(sut.runMenuEntry(requiresVision: true), .models(["gpt-4o"]))
    }

    func testVisionWorkflowHidesProviderWhoseModelsAllFilterOut() {
        // Filtered-to-empty must HIDE, not demote to a bare provider button —
        // a bare button would run the provider's default (text-only) model.
        let sut = provider(
            models: ["text-only"],
            supportsVision: false,
            details: [.init(modelId: "text-only", supportsVision: false)]
        )
        XCTAssertNil(sut.runMenuEntry(requiresVision: true))
    }

    func testModellessProviderKeepsBareButtonOnlyWhenVisionCapable() {
        XCTAssertEqual(
            provider(supportsVision: true).runMenuEntry(requiresVision: true),
            .providerOnly
        )
        XCTAssertNil(provider(supportsVision: false).runMenuEntry(requiresVision: true))
        // Non-vision workflow: bare button regardless.
        XCTAssertEqual(
            provider(supportsVision: false).runMenuEntry(requiresVision: false),
            .providerOnly
        )
    }

    func testEmptyDetailsWithVisionProviderKeepsAllModels() {
        // The Daniel bug from the opposite side: most installs have EMPTY
        // capability rows. Empty details + vision provider must not hide
        // anything.
        let sut = provider(models: ["a", "b"], supportsVision: true)
        XCTAssertEqual(sut.runMenuEntry(requiresVision: true), .models(["a", "b"]))
    }
}

/// #4187 — deriving `hasVisionNodes` from the workflow's nodes + the tool
/// registry, mirroring the engine's preflight rule (usesLLM && category ==
/// "vision"). Unknown tools and a missing registry fail OPEN (false → no
/// filtering); the engine is the enforcement point.
final class WorkflowSidebarItemVisionTests: XCTestCase {

    private func tool(_ name: String, category: String, usesLLM: Bool) -> ToolInfo {
        ToolInfo(
            name: name, displayName: name, description: "", category: category,
            icon: "gear", color: "blue", inputPorts: [], outputPorts: [],
            usesLLM: usesLLM, supportsBatch: false, supportsStreaming: false,
            supportsStructuredOutput: false, sortOrder: 0
        )
    }

    private func node(tool: String) -> [String: AnyCodable] {
        ["tool": AnyCodable(tool)]
    }

    func testVisionLLMToolRequiresVisionModel() {
        let registry = ["transcribe": tool("transcribe", category: "vision", usesLLM: true)]
        XCTAssertTrue(WorkflowSidebarItem.requiresVisionModel(
            nodes: [node(tool: "transcribe")], toolRegistry: registry
        ))
    }

    func testTextToolDoesNotRequireVisionModel() {
        let registry = ["summarize": tool("summarize", category: "text", usesLLM: true)]
        XCTAssertFalse(WorkflowSidebarItem.requiresVisionModel(
            nodes: [node(tool: "summarize")], toolRegistry: registry
        ))
    }

    func testVisionCategoryWithoutLLMDoesNotRequireVisionModel() {
        let registry = ["resize": tool("resize", category: "vision", usesLLM: false)]
        XCTAssertFalse(WorkflowSidebarItem.requiresVisionModel(
            nodes: [node(tool: "resize")], toolRegistry: registry
        ))
    }

    func testUnknownToolAndEmptyRegistryFailOpen() {
        XCTAssertFalse(WorkflowSidebarItem.requiresVisionModel(
            nodes: [node(tool: "mystery")], toolRegistry: [:]
        ))
    }

    func testMixedNodesRequireVisionWhenAnyVisionNodePresent() {
        let registry = [
            "summarize": tool("summarize", category: "text", usesLLM: true),
            "transcribe": tool("transcribe", category: "vision", usesLLM: true)
        ]
        XCTAssertTrue(WorkflowSidebarItem.requiresVisionModel(
            nodes: [node(tool: "summarize"), node(tool: "transcribe")],
            toolRegistry: registry
        ))
    }

    func testToolLookupIsCaseInsensitive() {
        // The registry is keyed by lowercased tool name (see
        // loadToolRegistry); node tool ids may differ in case.
        let registry = ["transcribe": tool("Transcribe", category: "Vision", usesLLM: true)]
        XCTAssertTrue(WorkflowSidebarItem.requiresVisionModel(
            nodes: [node(tool: "Transcribe")], toolRegistry: registry
        ))
    }

    func testHasVisionNodesDefaultsFalseOnDecode() throws {
        // hasVisionNodes is client-derived, never wire data.
        let json = Data("""
        {"id":"w1","name":"W","node_count":1,"edge_count":0,"is_enabled":true,
         "folder_path":"/","sort_order":0,"is_system":false,"untested":false,
         "created_at":"2026-05-11T08:00:00Z","updated_at":"2026-05-11T08:30:00Z"}
        """.utf8)
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let item = try decoder.decode(WorkflowSidebarItem.self, from: json)
        XCTAssertFalse(item.hasVisionNodes)
    }
}
