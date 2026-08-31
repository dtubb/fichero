@testable import Fichero
import XCTest

/// The COMPARE grammar's pure half (Daniel, 2026-08-30, reading-markup-coding
/// design item 6): which models a "Compare models…" press fans out over, and
/// how the runs are stamped comparable. No SwiftUI — the availability rules
/// and the inputs assembly are what can regress silently.
@MainActor
final class WorkflowCompareTests: XCTestCase {

    private func workflow(_ name: String) -> WorkflowSidebarItem {
        WorkflowSidebarItem(
            id: name,
            name: name,
            folderPath: "/Transcribe",
            sortOrder: 0,
            isDirectlyRunnable: true,
            acceptedInputs: ["documents"]
        )
    }

    private func step(_ name: String = "Transcribe") -> StagedWorkflowStep {
        StagedWorkflowStep(kind: .workflow(workflow(name)))
    }

    private func choice(_ model: String, provider: String = "openai") -> WorkflowBarModelChoice {
        WorkflowBarModelChoice(label: "\(model) · Text", provider: provider, model: model)
    }

    // MARK: - When the fan-out is offered at all

    func testSingleStepWithTwoModelsFansOut() {
        let runs = WorkflowComparePlanner.fanOut(
            staged: [step()],
            choices: [choice("gpt-4o"), choice("claude-3", provider: "anthropic")]
        )
        XCTAssertEqual(runs?.count, 2)
        XCTAssertEqual(runs?.map(\.model), ["gpt-4o", "claude-3"])
        XCTAssertEqual(runs?.map(\.provider), ["openai", "anthropic"])
    }

    func testEmptyChainOffersNoFanOut() {
        XCTAssertNil(WorkflowComparePlanner.fanOut(
            staged: [], choices: [choice("a"), choice("b")]
        ))
    }

    func testMultiStepChainOffersNoFanOut() {
        // N steps × M models is not a comparison anything can line up.
        XCTAssertNil(WorkflowComparePlanner.fanOut(
            staged: [step("One"), step("Two")],
            choices: [choice("a"), choice("b")]
        ))
    }

    func testSingleModelIsNotAComparison() {
        XCTAssertNil(WorkflowComparePlanner.fanOut(
            staged: [step()], choices: [choice("only")]
        ))
    }

    func testNonLLMToolOffersNoFanOut() {
        // A tool that never calls a model has no model to vary.
        let tool = StagedWorkflowStep(kind: .tool(
            name: "resize", displayName: "Resize", icon: "photo", usesLLM: false
        ))
        XCTAssertNil(WorkflowComparePlanner.fanOut(
            staged: [tool], choices: [choice("a"), choice("b")]
        ))
    }

    func testLLMToolFansOut() {
        let tool = StagedWorkflowStep(kind: .tool(
            name: "summarize", displayName: "Summarize", icon: "text.quote", usesLLM: true
        ))
        XCTAssertEqual(WorkflowComparePlanner.fanOut(
            staged: [tool], choices: [choice("a"), choice("b")]
        )?.count, 2)
    }

    // MARK: - Fan-out list hygiene

    func testDuplicateAndEmptyModelsAreDropped() {
        let runs = WorkflowComparePlanner.fanOut(
            staged: [step()],
            choices: [choice("a"), choice(""), choice("a"), choice("b")]
        )
        XCTAssertEqual(runs?.map(\.model), ["a", "b"])
    }

    func testDedupToSingleModelIsNotAComparison() {
        XCTAssertNil(WorkflowComparePlanner.fanOut(
            staged: [step()], choices: [choice("a"), choice("a")]
        ))
    }

    func testRunKeepsThePinMenuLabel() {
        // The confirmation must name a model exactly as the pin menu does.
        let runs = WorkflowComparePlanner.fanOut(
            staged: [step()], choices: [choice("a"), choice("b")]
        )
        XCTAssertEqual(runs?.first?.label, "a · Text")
    }

    // MARK: - Compare-group stamping

    func testFreshGroupIdsAreUniqueUUIDs() {
        let first = WorkflowComparePlanner.freshGroupId()
        let second = WorkflowComparePlanner.freshGroupId()
        XCTAssertNotEqual(first, second)
        XCTAssertNotNil(UUID(uuidString: first))
    }

    func testInputsCarryTheCompareGroup() {
        let inputs = WorkflowRunInputs.build(
            docIds: ["d1", "d2"],
            userContext: "",
            artifactTypeHint: nil,
            artifactStepNameHint: nil,
            compareGroup: "group-1"
        )
        XCTAssertEqual(inputs["compare_group"] as? String, "group-1")
        XCTAssertEqual(inputs["selected_doc_ids"] as? [String], ["d1", "d2"])
    }

    func testPlainRunsCarryNoCompareGroup() {
        // Absence, not empty string: the sibling lane groups by this key.
        for group in [nil, ""] as [String?] {
            let inputs = WorkflowRunInputs.build(
                docIds: ["d1"],
                userContext: "",
                artifactTypeHint: nil,
                artifactStepNameHint: nil,
                compareGroup: group
            )
            XCTAssertNil(inputs["compare_group"])
        }
    }

    func testInputsAssemblyKeepsFramingAndHints() {
        // The extraction from awaitWorkflowExecution must preserve the
        // existing behaviour: trimmed framing, hints only when non-empty.
        let inputs = WorkflowRunInputs.build(
            docIds: ["d1"],
            userContext: "  a diary  ",
            artifactTypeHint: "transcription",
            artifactStepNameHint: "",
            compareGroup: nil
        )
        XCTAssertEqual(inputs["user_context"] as? String, "a diary")
        XCTAssertEqual(inputs["artifact_type"] as? String, "transcription")
        XCTAssertNil(inputs["step_name"])
    }

    func testEmptyFramingIsAbsentNotEmpty() {
        let inputs = WorkflowRunInputs.build(
            docIds: ["d1"],
            userContext: "   ",
            artifactTypeHint: nil,
            artifactStepNameHint: nil,
            compareGroup: nil
        )
        XCTAssertNil(inputs["user_context"])
    }
}
