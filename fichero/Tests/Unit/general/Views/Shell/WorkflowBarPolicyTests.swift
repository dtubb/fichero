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

    // MARK: - Folder scope: This folder vs Everything inside (2026-09-06)

    private func folderSnapshot(
        childIds: [String] = ["c1", "c2", "c3"]
    ) -> WorkflowBarPolicy.SelectionSnapshot {
        WorkflowBarPolicy.SelectionSnapshot(
            browserSelection: ["folder-1"],
            folderSubjectId: "folder-1",
            folderSubjectName: "Marshall Diaries",
            folderChildIds: childIds
        )
    }

    func testFolderSubjectOffersThisFolderAndEverythingInside() {
        let options = WorkflowBarPolicy.scopeMenuOptions(from: folderSnapshot())
        let labels = options.map(\.label)
        XCTAssertTrue(labels.contains("This folder"))
        XCTAssertTrue(labels.contains("Everything inside — 3 items"))
        // The bare "1 item" document row for the same folder id is suppressed
        // in favour of the two clearer folder rows.
        XCTAssertFalse(labels.contains("1 item"))
    }

    func testFolderContentsScopeRunsOnTheChildIdsNotTheFolder() {
        let scope = WorkflowBarPolicy.RunScope.folderContents(
            folderId: "folder-1", folderName: "Marshall Diaries",
            childIds: ["c1", "c2", "c3"]
        )
        XCTAssertEqual(scope.documentIds, ["c1", "c2", "c3"])
        XCTAssertEqual(scope.target, .documents(count: 3))
        XCTAssertEqual(WorkflowBarPolicy.scopeDetail(scope), "3 items in Marshall Diaries")
    }

    func testEverythingInsideOverrideRefreshesChildCountFromSnapshot() {
        // Chosen while children were still loading (empty), then the cache
        // fills — the override must reflect the fresh count, not the frozen one.
        let stale = WorkflowBarPolicy.RunScope.folderContents(
            folderId: "folder-1", folderName: "Marshall Diaries", childIds: []
        )
        let resolved = WorkflowBarPolicy.resolveRunScope(
            folderSnapshot(childIds: ["c1", "c2"]), override: stale
        )
        XCTAssertEqual(resolved.documentIds, ["c1", "c2"])
    }

    func testFolderContentsOverrideDropsWhenTheFolderLeaves() {
        let chosen = WorkflowBarPolicy.RunScope.folderContents(
            folderId: "folder-1", folderName: "Marshall Diaries", childIds: ["c1"]
        )
        // A snapshot where the folder is no longer the subject — the override
        // yields back to the ladder rather than running on an off-screen folder.
        let gone = WorkflowBarPolicy.SelectionSnapshot(browserSelection: ["other"])
        let resolved = WorkflowBarPolicy.resolveRunScope(gone, override: chosen)
        XCTAssertEqual(resolved, .documents(ids: ["other"]))
    }

    func testThisFolderOverrideSurvivesWhenTheFolderIsNotThePreviewedDoc() {
        // "This folder" is a `.detailDocument(folderId)` override. The folder is
        // selected in the browser but NOT the previewed detail document, so
        // keying visibility on the detail doc alone silently dropped the choice
        // back to the ladder — which sends [folderId] and lets the engine expand
        // it to every file, the exact "it still runs on every file" bug.
        let chosen = WorkflowBarPolicy.RunScope.detailDocument(
            id: "folder-1", name: "Marshall Diaries"
        )
        let resolved = WorkflowBarPolicy.resolveRunScope(folderSnapshot(), override: chosen)
        XCTAssertEqual(resolved, chosen)
        XCTAssertEqual(resolved.documentIds, ["folder-1"])
    }

    func testExpandFoldersIsOffOnlyForTheThisFolderScope() {
        // "This folder" — the lone folder subject chosen as a single document —
        // must NOT be expanded to its files.
        XCTAssertFalse(
            WorkflowBarPolicy.expandFolders(
                for: .detailDocument(id: "folder-1", name: "Marshall Diaries"),
                folderSubjectId: "folder-1"
            )
        )
        // "Everything inside" already carries the child ids; the engine still
        // expands each child (subfolders, PDFs) normally.
        XCTAssertTrue(
            WorkflowBarPolicy.expandFolders(
                for: .folderContents(
                    folderId: "folder-1", folderName: "Marshall Diaries",
                    childIds: ["c1", "c2"]
                ),
                folderSubjectId: "folder-1"
            )
        )
        // A plain folder selection with no explicit "This folder" choice keeps
        // the engine's default expansion.
        XCTAssertTrue(
            WorkflowBarPolicy.expandFolders(
                for: .documents(ids: ["folder-1"]), folderSubjectId: "folder-1"
            )
        )
        // A previewed ordinary document that happens to be the detail scope is
        // never a folder subject, so expansion stays on (a no-op for a leaf).
        XCTAssertTrue(
            WorkflowBarPolicy.expandFolders(
                for: .detailDocument(id: "page-1", name: "Hoja"),
                folderSubjectId: nil
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
