@testable import Fichero
import XCTest

/// Policy tests for the capability bar (2026-08-28). The bar is a projection
/// of the selection through each workflow's server-declared `accepted_inputs`,
/// so the behaviour that can regress — which verbs appear for which selection,
/// and never offering one that would fail — is asserted here rather than on
/// pixels.
@MainActor
final class WorkflowBarPolicyTests: XCTestCase {

    private func workflow(
        _ name: String,
        folder: String = "/Transcribe",
        accepts: [String] = ["documents"],
        runnable: Bool = true,
        sortOrder: Int = 0
    ) -> WorkflowSidebarItem {
        WorkflowSidebarItem(
            id: name,
            name: name,
            folderPath: folder,
            sortOrder: sortOrder,
            isDirectlyRunnable: runnable,
            acceptedInputs: accepts
        )
    }

    // MARK: - Filtering by what is selected

    func testDocumentSelectionOffersDocumentVerbs() {
        let families = WorkflowBarPolicy.families(
            from: [workflow("Transcribe")],
            target: .documents(count: 3)
        )
        XCTAssertEqual(families.count, 1)
        XCTAssertEqual(families.first?.workflows.first?.name, "Transcribe")
    }

    func testTextSelectionHidesVerbsThatCannotTakeText() {
        // The whole point: Transcribe wants pixels, so a highlighted passage
        // must not offer it. Offering a verb that the engine would then refuse
        // is worse than not offering it at all.
        let workflows = [
            workflow("Transcribe", accepts: ["documents"]),
            workflow("Catalogue", folder: "/Catalogue", accepts: ["documents", "text"])
        ]
        let families = WorkflowBarPolicy.families(
            from: workflows,
            target: .text("dize que llevaua")
        )
        XCTAssertEqual(families.map(\.title), ["Catalogue"])
    }

    func testNothingSelectedOffersNothing() {
        XCTAssertTrue(
            WorkflowBarPolicy.families(from: [workflow("Transcribe")], target: .nothing).isEmpty
        )
    }

    func testEmptyDocumentSelectionOffersNothing() {
        // A verb with nothing to act on is a button that lies.
        XCTAssertTrue(
            WorkflowBarPolicy.families(
                from: [workflow("Transcribe")],
                target: .documents(count: 0)
            ).isEmpty
        )
    }

    func testComponentWorkflowsAreNotOfferedAsVerbs() {
        // direct_runnable=false means it only runs inside a parent; the engine
        // refuses it directly, so the bar must not present it.
        let families = WorkflowBarPolicy.families(
            from: [workflow("Review 2 (component)", runnable: false)],
            target: .documents(count: 1)
        )
        XCTAssertTrue(families.isEmpty)
    }

    // MARK: - Grouping

    func testNestedFoldersCollapseIntoOneFamily() {
        // "/Detect Regions/VLM" and "/Detect Regions" are one verb with
        // variants, not two verbs.
        let workflows = [
            workflow("Apple Vision", folder: "/Detect Regions"),
            workflow("VLM", folder: "/Detect Regions/VLM")
        ]
        let families = WorkflowBarPolicy.families(from: workflows, target: .documents(count: 1))
        XCTAssertEqual(families.count, 1)
        XCTAssertEqual(families.first?.workflows.count, 2)
    }

    func testVariantsAreOrderedByTheEnginesSortOrder() {
        let workflows = [
            workflow("second", sortOrder: 2),
            workflow("first", sortOrder: 1)
        ]
        let families = WorkflowBarPolicy.families(from: workflows, target: .documents(count: 1))
        XCTAssertEqual(families.first?.workflows.map(\.name), ["first", "second"])
    }

    func testAnUnrecognisedFolderStillGetsAFamilyAndASymbol() {
        // A preset in a folder nobody anticipated must stay runnable.
        let families = WorkflowBarPolicy.families(
            from: [workflow("Odd One", folder: "/Something New")],
            target: .documents(count: 1)
        )
        XCTAssertEqual(families.map(\.title), ["Something New"])
        XCTAssertFalse(families.first?.symbol.isEmpty ?? true)
    }

    func testRootLevelWorkflowGetsAFamilyRatherThanVanishing() {
        let families = WorkflowBarPolicy.families(
            from: [workflow("Loose", folder: "/")],
            target: .documents(count: 1)
        )
        XCTAssertEqual(families.map(\.title), ["Other"])
    }

    // MARK: - The target chip

    func testTargetLabelStatesTheScopeBeforeTheRun() {
        XCTAssertEqual(WorkflowBarPolicy.targetLabel(.documents(count: 1)), "1 item")
        XCTAssertEqual(WorkflowBarPolicy.targetLabel(.documents(count: 92)), "92 items")
        XCTAssertEqual(WorkflowBarPolicy.targetLabel(.text("one")), "1 word")
        XCTAssertEqual(WorkflowBarPolicy.targetLabel(.text("dize que llevaua")), "3 words")
        XCTAssertNil(WorkflowBarPolicy.targetLabel(.nothing))
    }

    // MARK: - Explaining an empty bar

    func testAnEmptyBarSaysWhy() {
        // An empty bar with no explanation reads as a broken app.
        XCTAssertNotNil(WorkflowBarPolicy.emptyReason(from: [], target: .nothing))
        XCTAssertNotNil(
            WorkflowBarPolicy.emptyReason(
                from: [workflow("Transcribe", accepts: ["documents"])],
                target: .text("passage")
            )
        )
    }

    func testAPopulatedBarHasNoEmptyReason() {
        XCTAssertNil(
            WorkflowBarPolicy.emptyReason(
                from: [workflow("Transcribe")],
                target: .documents(count: 1)
            )
        )
    }
}
