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
        // The the user bug from the opposite side: most installs have EMPTY
        // capability rows. Empty details + vision provider must not hide
        // anything.
        let sut = provider(models: ["a", "b"], supportsVision: true)
        XCTAssertEqual(sut.runMenuEntry(requiresVision: true), .models(["a", "b"]))
    }
}

/// #3804 — "does this workflow need a vision model?" is the SERVER's answer,
/// read from `requires_vision`. The client used to recompute it from its own
/// node list (`WorkflowSidebarItem.requiresVisionModel`), which could only
/// see the parent's nodes: a workflow that delegates its vision work to a
/// `sub_workflow` child looked text-only, so the Run menu offered text-only
/// models the engine's preflight then rejected. The engine descends into
/// children (cycle-guarded); the client must not second-guess it.
final class WorkflowRequiresVisionWireTests: XCTestCase {

    private func responseJSON(
        nodes: String = "[]",
        requiresVisionKey: String = ""
    ) -> Data {
        Data("""
        {"id":"wf-1","name":"Parent","description":"",
         "provider":"openai","model":"gpt-4o",
         "nodes":\(nodes),"edges":[],
         "folder_path":"/","sort_order":0,
         "is_system":false,"untested":false\(requiresVisionKey)}
        """.utf8)
    }

    /// THE case the client computation got wrong: the parent's own nodes are
    /// a text tool and a sub_workflow reference — nothing here `usesLLM` in
    /// the "vision" category — yet the workflow requires vision because the
    /// child does. Only the server can see that.
    func testVisionRequirementLivingOnlyInAChildIsReported() throws {
        let parentNodes = """
        [{"id":"n1","tool":"summarize_file"},
         {"id":"n2","tool":"sub_workflow","workflow_ref":"child-with-transcribe"}]
        """
        let resp = try JSONDecoder().decode(
            WorkflowResponse.self,
            from: responseJSON(nodes: parentNodes, requiresVisionKey: ",\"requires_vision\":true")
        )
        XCTAssertTrue(
            resp.requiresVision,
            "A parent whose vision node lives in a sub_workflow child must still require vision."
        )

        let item = WorkflowSidebarItem(name: resp.name, requiresVision: resp.requiresVision)
        XCTAssertTrue(item.requiresVision)
        XCTAssertNil(
            LLMProvider(id: "p", name: "P", models: ["m"], available: true, supportsVision: false)
                .runMenuEntry(requiresVision: item.requiresVision),
            "A text-only provider must drop out of the Run menu for a vision workflow."
        )
    }

    func testTextOnlyWorkflowDoesNotRequireVision() throws {
        let resp = try JSONDecoder().decode(
            WorkflowResponse.self,
            from: responseJSON(
                nodes: "[{\"id\":\"n1\",\"tool\":\"summarize_file\"}]",
                requiresVisionKey: ",\"requires_vision\":false"
            )
        )
        XCTAssertFalse(resp.requiresVision)
    }

    /// Absent key (older engine) must fail OPEN to an unfiltered menu, never
    /// hide models the user could legitimately pick. The engine stays the
    /// enforcement point.
    func testAbsentRequiresVisionFailsOpen() throws {
        let resp = try JSONDecoder().decode(WorkflowResponse.self, from: responseJSON())
        XCTAssertFalse(resp.requiresVision)
    }

    /// Decoding a sidebar row without the key keeps the same fail-open
    /// default, so a persisted pre-#3804 row does not start hiding models.
    func testSidebarItemDefaultsFalseWhenKeyAbsent() throws {
        let json = Data("""
        {"id":"w1","name":"W","node_count":1,"edge_count":0,"is_enabled":true,
         "folder_path":"/","sort_order":0,"is_system":false,"untested":false,
         "created_at":"2026-05-11T08:00:00Z","updated_at":"2026-05-11T08:30:00Z"}
        """.utf8)
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        XCTAssertFalse(try decoder.decode(WorkflowSidebarItem.self, from: json).requiresVision)
    }

    /// The deleted client computation must stay deleted. A future edit that
    /// re-derives vision from the node list would silently reintroduce the
    /// sub-workflow blind spot, and nothing else in the suite would notice —
    /// the parent's nodes decode fine, they just answer the wrong question.
    func testNoClientSideVisionDerivationRemains() throws {
        let app = try AppSource.root()
        var offenders: [String] = []
        let walker = FileManager.default.enumerator(atPath: app.path)
        while let relative = walker?.nextObject() as? String {
            guard relative.hasSuffix(".swift") else { continue }
            let source = try String(
                contentsOf: app.appendingPathComponent(relative), encoding: .utf8
            )
            // The old derivation's two fingerprints: the removed helper, and
            // the category test it performed inline.
            if source.contains("requiresVisionModel(")
                || source.contains("hasVisionNodes") {
                offenders.append(relative)
            }
        }
        XCTAssertEqual(
            offenders, [],
            "Client-side vision derivation is back in \(offenders) — it cannot see "
            + "sub_workflow children, so it will disagree with the engine's preflight. "
            + "Read `requires_vision` off the workflow response instead."
        )
    }
}

