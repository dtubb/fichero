@testable import Fichero
import XCTest

/// The run-scope ladder (Daniel, 2026-08-29): the bar follows the selection
/// the user can SEE — Preview marquee > inspector regions > inspector
/// artifact > browser selection > detail document. Its own class because the
/// ladder is its own decision (and the policy class body is at the length
/// limit).
@MainActor
final class WorkflowBarRunScopeTests: XCTestCase {

    private func snapshot(
        marqueeDocumentId: String? = nil,
        marqueeRect: CGRect? = nil,
        marqueeDocumentName: String? = nil,
        regionIds: [String] = [],
        regionParent: String? = nil,
        regionParentName: String? = nil,
        artifactId: String? = nil,
        artifactDocumentId: String? = nil,
        artifactDisplayName: String? = nil,
        artifactType: String? = nil,
        artifactStepName: String? = nil,
        artifactDocumentName: String? = nil,
        browserSelection: [String] = [],
        detailId: String? = nil,
        detailName: String? = nil
    ) -> WorkflowBarPolicy.SelectionSnapshot {
        WorkflowBarPolicy.SelectionSnapshot(
            marqueeDocumentId: marqueeDocumentId,
            marqueeRect: marqueeRect,
            marqueeDocumentName: marqueeDocumentName,
            regionIds: regionIds,
            regionParentDocumentId: regionParent,
            regionParentName: regionParentName,
            artifactId: artifactId,
            artifactDocumentId: artifactDocumentId,
            artifactDisplayName: artifactDisplayName,
            artifactType: artifactType,
            artifactStepName: artifactStepName,
            artifactDocumentName: artifactDocumentName,
            browserSelection: browserSelection,
            detailDocumentId: detailId,
            detailDocumentName: detailName
        )
    }

    func testMarqueeSelectionOutranksEveryOtherRung() {
        // An ephemeral crop drawn in Preview is the topmost rung: it beats
        // region rows, artifact focus, and the browser alike.
        let rect = CGRect(x: 0.1, y: 0.2, width: 0.3, height: 0.4)
        let scope = WorkflowBarPolicy.resolveRunScope(snapshot(
            marqueeDocumentId: "page-1",
            marqueeRect: rect,
            marqueeDocumentName: "4_Hoja_531_Verso",
            regionIds: ["r1"],
            regionParent: "page-1",
            artifactId: "a1",
            artifactDocumentId: "page-1",
            browserSelection: ["d1", "d2"],
            detailId: "page-1"
        ))
        XCTAssertEqual(
            scope,
            .marqueeSelection(documentId: "page-1", rect: rect, documentName: "4_Hoja_531_Verso")
        )
        // The source document stands in until ▶ materializes the crop child.
        XCTAssertEqual(scope.documentIds, ["page-1"])
        XCTAssertEqual(scope.target, .documents(count: 1))
        XCTAssertEqual(
            WorkflowBarPolicy.scopeDetail(scope),
            "a selection of 4_Hoja_531_Verso"
        )
    }

    func testMarqueeFromAPageTheUserLeftOrWithNoAreaDropsOut() {
        // Drawn on page-1 but the user now previews page-2 — not the
        // selection they can see.
        let stale = WorkflowBarPolicy.resolveRunScope(snapshot(
            marqueeDocumentId: "page-1",
            marqueeRect: CGRect(x: 0, y: 0, width: 0.5, height: 0.5),
            regionIds: ["r1"],
            regionParent: "page-2",
            detailId: "page-2"
        ))
        XCTAssertEqual(stale, .regions(ids: ["r1"], parentName: nil))
        // A zero-area rect is a click, not a selection.
        let empty = WorkflowBarPolicy.resolveRunScope(snapshot(
            marqueeDocumentId: "page-1",
            marqueeRect: CGRect(x: 0.5, y: 0.5, width: 0, height: 0),
            detailId: "page-1",
            detailName: "Hoja"
        ))
        XCTAssertEqual(empty, .detailDocument(id: "page-1", name: "Hoja"))
    }

    func testInspectorRegionSelectionOutranksEverything() {
        let scope = WorkflowBarPolicy.resolveRunScope(snapshot(
            regionIds: ["r1", "r2", "r3"],
            regionParent: "page-1",
            regionParentName: "4_Hoja_531_Verso",
            artifactId: "a1",
            artifactDocumentId: "page-1",
            browserSelection: ["d1", "d2"],
            detailId: "page-1"
        ))
        XCTAssertEqual(scope, .regions(ids: ["r1", "r2", "r3"], parentName: "4_Hoja_531_Verso"))
        XCTAssertEqual(scope.documentIds, ["r1", "r2", "r3"])
        XCTAssertEqual(scope.target, .documents(count: 3))
    }

    func testRegionChipNamesTheRegionsAndTheirPage() {
        // The chip must NAME what it resolved to, not merely count it.
        XCTAssertEqual(
            WorkflowBarPolicy.scopeDetail(
                .regions(ids: ["r1", "r2", "r3", "r4", "r5"], parentName: "4_Hoja_531_Verso")
            ),
            "5 regions of 4_Hoja_531_Verso"
        )
        XCTAssertEqual(
            WorkflowBarPolicy.scopeDetail(.regions(ids: ["r1"], parentName: nil)),
            "1 region"
        )
    }

    func testRegionSelectionFromAPageTheUserLeftDropsOut() {
        // The regions belong to page-1 but the user is now inspecting
        // page-2: not the selection they can see, so the ladder falls
        // through to the browser rung.
        let scope = WorkflowBarPolicy.resolveRunScope(snapshot(
            regionIds: ["r1"],
            regionParent: "page-1",
            browserSelection: ["d1", "d2"],
            detailId: "page-2"
        ))
        XCTAssertEqual(scope, .documents(ids: ["d1", "d2"]))
    }

    func testFocusedArtifactScopesTheRunToItsDocumentWithHints() {
        let scope = WorkflowBarPolicy.resolveRunScope(snapshot(
            artifactId: "a1",
            artifactDocumentId: "page-1",
            artifactDisplayName: "Transcription Review",
            artifactType: "transcription_review",
            artifactStepName: "final",
            artifactDocumentName: "4_Hoja_531_Verso",
            browserSelection: ["page-1"],
            detailId: "page-1"
        ))
        guard case .artifact(let documentId, let artifactId, _, _, let type, let step) = scope else {
            return XCTFail("expected artifact scope, got \(scope)")
        }
        XCTAssertEqual(documentId, "page-1")
        XCTAssertEqual(artifactId, "a1")
        XCTAssertEqual(type, "transcription_review")
        XCTAssertEqual(step, "final")
        XCTAssertEqual(scope.documentIds, ["page-1"])
        XCTAssertEqual(
            WorkflowBarPolicy.scopeDetail(scope),
            "Transcription Review of 4_Hoja_531_Verso"
        )
    }

    func testStaleArtifactFocusFromAnotherDocumentDropsOut() {
        // The focused artifact belongs to a document the user has left.
        let scope = WorkflowBarPolicy.resolveRunScope(snapshot(
            artifactId: "a1",
            artifactDocumentId: "page-1",
            browserSelection: ["d9"],
            detailId: "d9"
        ))
        XCTAssertEqual(scope, .documents(ids: ["d9"]))
    }

    func testDeliberateMultiSelectOutranksALingeringArtifactFocus() {
        // Selecting five documents in the browser is unmistakably the
        // selection the user can see, even while an artifact stays focused.
        let scope = WorkflowBarPolicy.resolveRunScope(snapshot(
            artifactId: "a1",
            artifactDocumentId: "page-1",
            browserSelection: ["page-1", "d2", "d3", "d4", "d5"],
            detailId: "page-1"
        ))
        XCTAssertEqual(scope, .documents(ids: ["page-1", "d2", "d3", "d4", "d5"]))
    }

    func testBrowserSelectionThenDetailThenNothing() {
        XCTAssertEqual(
            WorkflowBarPolicy.resolveRunScope(snapshot(browserSelection: ["d1", "d2"])),
            .documents(ids: ["d1", "d2"])
        )
        XCTAssertEqual(
            WorkflowBarPolicy.resolveRunScope(snapshot(detailId: "d1", detailName: "Hoja 531")),
            .detailDocument(id: "d1", name: "Hoja 531")
        )
        let nothing = WorkflowBarPolicy.resolveRunScope(snapshot())
        XCTAssertEqual(nothing, .nothing)
        XCTAssertEqual(nothing.documentIds, [])
        XCTAssertEqual(nothing.target, .nothing)
    }

    func testDocumentScopesLeaveTheChipToTheCallersTypedNouns() {
        // scopeDetail names only what the ladder resolved ABOVE the browser;
        // document scopes keep the existing "3 images"/"5 pages" labelling.
        XCTAssertNil(WorkflowBarPolicy.scopeDetail(.documents(ids: ["d1", "d2"])))
        XCTAssertNil(WorkflowBarPolicy.scopeDetail(.detailDocument(id: "d1", name: "Hoja")))
        XCTAssertNil(WorkflowBarPolicy.scopeDetail(.nothing))
    }

    // MARK: - Explicit override from the subject chip's menu
    // (Daniel, 2026-08-29 evening: the chip that names the scope is
    // clickable to CHANGE it; "Automatic" restores the ladder)

    func testChosenOverrideOutranksTheAutomaticLadder() {
        // Regions are selected (the ladder's pick), but the user aimed the
        // run at the browser selection from the menu.
        let live = snapshot(
            regionIds: ["r1", "r2"],
            regionParent: "page-1",
            browserSelection: ["d1", "d2"],
            detailId: "page-1"
        )
        let chosen = WorkflowBarPolicy.RunScope.documents(ids: ["d1", "d2"])
        XCTAssertEqual(
            WorkflowBarPolicy.resolveRunScope(live, override: chosen),
            chosen
        )
        // nil override = Automatic: back to the ladder's pick.
        XCTAssertEqual(
            WorkflowBarPolicy.resolveRunScope(live, override: nil),
            .regions(ids: ["r1", "r2"], parentName: nil)
        )
    }

    func testStaleOverrideYieldsBackToTheLadder() {
        // The override named a browser selection that has since changed —
        // running on the OLD ids would act on something invisible.
        let live = snapshot(browserSelection: ["d9"], detailId: "d9")
        XCTAssertEqual(
            WorkflowBarPolicy.resolveRunScope(
                live, override: .documents(ids: ["d1", "d2"])
            ),
            .documents(ids: ["d9"])
        )
    }

    func testArtifactTypeOverrideHoldsWhileItsDocumentIsInspected() {
        let chosen = WorkflowBarPolicy.RunScope.artifact(
            documentId: "page-1", artifactId: nil,
            displayName: "Transcription Review", documentName: "Hoja",
            artifactType: "transcription_review", stepName: nil
        )
        let inspected = snapshot(browserSelection: ["page-1"], detailId: "page-1")
        XCTAssertEqual(
            WorkflowBarPolicy.resolveRunScope(inspected, override: chosen),
            chosen
        )
        // The user moved to another document: the override is stale.
        let moved = snapshot(browserSelection: ["d2"], detailId: "d2")
        XCTAssertEqual(
            WorkflowBarPolicy.resolveRunScope(moved, override: chosen),
            .documents(ids: ["d2"])
        )
    }

    func testMenuOffersAutomaticFirstThenRungsThenArtifactTypes() {
        let options = WorkflowBarPolicy.scopeMenuOptions(from: snapshot(
            regionIds: ["r1"],
            regionParent: "page-1",
            regionParentName: "Hoja",
            artifactId: "a1",
            artifactDocumentId: "page-1",
            artifactDisplayName: "Transcription",
            artifactDocumentName: "Hoja",
            browserSelection: ["page-1", "d2"],
            detailId: "page-1",
            detailName: "Hoja"
        ))
        XCTAssertEqual(options.first?.label, "Automatic")
        XCTAssertNil(options.first?.scope)
        XCTAssertTrue(options.contains { $0.id == "regions" && $0.label == "1 region of Hoja" })
        XCTAssertTrue(options.contains { $0.id == "artifact" })
        XCTAssertTrue(options.contains { $0.id == "documents" && $0.label == "2 items" })
        // The artifacts_source targets, offered by TYPE and named like the chip.
        XCTAssertTrue(options.contains {
            $0.id == "artifact-type-transcription_review"
                && $0.label == "Transcription Review of Hoja"
        })
        if case .artifact(let documentId, let artifactId, _, _, let type, _)? =
            options.first(where: { $0.id == "artifact-type-translation" })?.scope {
            XCTAssertEqual(documentId, "page-1")
            XCTAssertNil(artifactId)
            XCTAssertEqual(type, "translation")
        } else {
            XCTFail("expected an artifact-type option for translation")
        }
    }

    func testMenuOffersNothingButAutomaticWhenNothingIsThere() {
        let options = WorkflowBarPolicy.scopeMenuOptions(from: snapshot())
        XCTAssertEqual(options.map(\.id), ["automatic"])
    }
}
