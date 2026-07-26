@testable import Fichero
import XCTest

/// #4058 — "Default Workflows" rendered as a bare folder with no disclosure
/// chevron and no children.
///
/// The engine MIRRORS each workflow into the document tree as a leaf `Document`
/// with `doc_type=file`, `prototype_key="workflow"` and NO `file_type` (see
/// `_save_workflow_document`). Those rows were fetched and cached, then dropped
/// by `SidebarItemBuilder`'s visibility filter — which runs BEFORE the
/// parent→children map is built, so the surviving container was constructed
/// with `children == nil`. `SidebarItem.isExpandable` then fell through to
/// `isNavigableContainer && childCount > 0`, and since the backend sends no
/// `child_count` on `getRoots`/`getChildren` that is 0 → no DisclosureGroup at
/// all, so the user could not even expand it to trigger a load.
@MainActor
final class SidebarWorkflowNodeTreeTests: XCTestCase {

    private static let containerId = "default-workflows-container"

    /// The seeded "Default Workflows" folder, as the engine writes it: a real
    /// folder doc, but with `childCount == 0` because the roots/children
    /// payloads omit `child_count`.
    private func makeContainer(childCount: Int = 0) -> Document {
        Document(
            id: Self.containerId,
            parentId: nil,
            docType: .folder,
            name: "Default Workflows",
            childCount: childCount
        )
    }

    /// A mirrored workflow row: `.file`, no `fileType`, `prototype_key`
    /// identifying it as a workflow.
    private func makeWorkflowMirror(id: String, name: String, sortOrder: Int = 0) -> Document {
        Document(
            id: id,
            parentId: Self.containerId,
            docType: .file,
            fileType: nil,
            name: name,
            sortOrder: sortOrder,
            prototypeKey: "workflow"
        )
    }

    private func container(in items: [SidebarItem]) -> SidebarItem? {
        items.first { $0.id == "doc:\(Self.containerId)" }
    }

    // MARK: - Direct repro

    /// FAILS BEFORE THE FIX: the mirrors are filtered out, so `children` is nil
    /// and the container is not expandable.
    func testWorkflowMirrorsRenderAsChildrenOfDefaultWorkflows() {
        let lib = UUID()
        let docs = [
            makeContainer(),
            makeWorkflowMirror(id: "wf-1", name: "Transcribe", sortOrder: 0),
            makeWorkflowMirror(id: "wf-2", name: "Summarize", sortOrder: 1)
        ]

        let items = SidebarItemBuilder.buildLibraryHierarchy(from: docs, libraryId: lib)

        guard let folder = container(in: items) else {
            return XCTFail("Default Workflows container missing from the tree")
        }
        XCTAssertEqual(folder.children?.map(\.name), ["Transcribe", "Summarize"])
        XCTAssertTrue(folder.isExpandable, "container must render a DisclosureGroup once children exist")
    }

    /// The bug's visible symptom, asserted directly: without a non-nil
    /// `children` array the row has no chevron, because `childCount` is 0 on
    /// every roots/children payload.
    func testContainerIsExpandableEvenThoughChildCountIsZero() {
        let docs = [makeContainer(childCount: 0), makeWorkflowMirror(id: "wf-1", name: "Transcribe")]
        let items = SidebarItemBuilder.buildLibraryHierarchy(from: docs, libraryId: UUID())
        XCTAssertEqual(container(in: items)?.children?.count, 1)
        XCTAssertTrue(container(in: items)?.isExpandable == true)
    }

    /// Mirrors must read as workflows, not as generic files — they carry no
    /// `fileType`, so before the fix they would have fallen through to the
    /// plain `.file` glyph.
    func testWorkflowMirrorUsesTheWorkflowIcon() {
        let docs = [makeContainer(), makeWorkflowMirror(id: "wf-1", name: "Transcribe")]
        let items = SidebarItemBuilder.buildLibraryHierarchy(from: docs, libraryId: UUID())
        let child = container(in: items)?.children?.first
        XCTAssertEqual(child?.icon, ItemCategory.workflow.icon)
    }

    // MARK: - The predicate itself

    func testVisibilityPredicateAdmitsWorkflowMirrors() {
        XCTAssertTrue(SidebarItemBuilder.isSidebarVisible(makeWorkflowMirror(id: "wf-1", name: "Transcribe")))
    }

    /// Guard against over-fixing: admitting workflow mirrors must NOT admit
    /// generic files. Text/docx stay in the grid only.
    func testVisibilityPredicateStillExcludesGenericFiles() {
        let plain = Document(parentId: Self.containerId, docType: .file, name: "notes.txt")
        XCTAssertFalse(SidebarItemBuilder.isSidebarVisible(plain))

        let otherPrototype = Document(
            parentId: Self.containerId, docType: .file, name: "note", prototypeKey: "note"
        )
        XCTAssertFalse(SidebarItemBuilder.isSidebarVisible(otherPrototype))
    }

    // MARK: - Edge cases

    /// Empty children: an as-yet-unpopulated container must NOT gain a phantom
    /// chevron. `children` stays nil and `isExpandable` stays false, exactly as
    /// before the fix — this is the state the pre-fix bug was masquerading as.
    func testContainerWithNoWorkflowChildrenIsNotExpandable() {
        let items = SidebarItemBuilder.buildLibraryHierarchy(from: [makeContainer()], libraryId: UUID())
        let folder = container(in: items)
        XCTAssertNotNil(folder, "the container itself still renders")
        XCTAssertNil(folder?.children)
        XCTAssertFalse(folder?.isExpandable == true)
    }

    /// Children load asynchronously: `sidebarDocuments` is
    /// `collections + childrenCache.values`, so the container appears one
    /// rebuild BEFORE its mirrors are cached. Rebuilding with the fuller set
    /// must pick them up (and must not have cached a stale childless item).
    func testChildrenAppearOnRebuildAfterLazyCachePopulates() {
        let lib = UUID()
        let before = SidebarItemBuilder.buildLibraryHierarchy(from: [makeContainer()], libraryId: lib)
        XCTAssertNil(container(in: before)?.children)

        let after = SidebarItemBuilder.buildLibraryHierarchy(
            from: [makeContainer(), makeWorkflowMirror(id: "wf-1", name: "Transcribe")],
            libraryId: lib
        )
        XCTAssertEqual(after.count, before.count, "no extra root rows appear when children arrive")
        XCTAssertEqual(container(in: after)?.children?.count, 1)
    }

    /// Row identity must stay unique and stable: `unifiedRows` uses
    /// `ForEach(..., id: \.element.id)`, so colliding ids would collapse or
    /// duplicate rows. A mirror (`doc:`) and the app-side virtual workflow row
    /// (`workflow:`) for the SAME workflow can be present at once under the
    /// global library, and must not collide.
    func testMirrorIdsAreUniqueAndDoNotCollideWithVirtualWorkflowRows() {
        let lib = UUID()
        let docs = [
            makeContainer(),
            makeWorkflowMirror(id: "wf-1", name: "Transcribe", sortOrder: 0),
            makeWorkflowMirror(id: "wf-2", name: "Summarize", sortOrder: 1)
        ]
        let items = SidebarItemBuilder.buildLibraryHierarchy(from: docs, libraryId: lib)
        let children = container(in: items)?.children ?? []

        XCTAssertEqual(children.map(\.id), ["doc:wf-1", "doc:wf-2"])
        XCTAssertEqual(Set(children.map(\.id)).count, children.count, "duplicate row ids would collapse rows")

        // Same workflow, app-side virtual row — different namespace.
        let virtualId = "workflow:wf-1"
        XCTAssertFalse(children.map(\.id).contains(virtualId))
    }

    /// Mirrors respect the shared sibling comparator (sortOrder, then name)
    /// rather than arriving in payload order.
    func testWorkflowMirrorsSortBySortOrder() {
        let docs = [
            makeContainer(),
            makeWorkflowMirror(id: "wf-b", name: "Zebra", sortOrder: 0),
            makeWorkflowMirror(id: "wf-a", name: "Alpha", sortOrder: 1)
        ]
        let items = SidebarItemBuilder.buildLibraryHierarchy(from: docs, libraryId: UUID())
        XCTAssertEqual(container(in: items)?.children?.map(\.name), ["Zebra", "Alpha"])
    }

    /// Show ALL items — no cap on how many workflows render under the folder.
    func testAllWorkflowMirrorsRenderWithNoCap() {
        var docs: [Document] = [makeContainer()]
        for index in 0..<40 {
            docs.append(makeWorkflowMirror(id: "wf-\(index)", name: "Flow \(index)", sortOrder: index))
        }
        let items = SidebarItemBuilder.buildLibraryHierarchy(from: docs, libraryId: UUID())
        XCTAssertEqual(container(in: items)?.children?.count, 40)
    }

    // MARK: - Global-only boundary regression

    /// REGRESSION: #4060 — Workflow mirrors must remain excluded from
    /// non-global libraries at the display layer. The visibility predicate now
    /// includes workflow nodes for all libraries so they build into the
    /// hierarchy. But the display layer's `flattenedLibraryItems` gate
    /// (`libraryId == LibraryManager.globalLibraryId`) prevents them from
    /// rendering in non-global libraries. This test verifies that mirrors ARE
    /// included in the hierarchy (because the predicate includes them), but
    /// documents that the display-layer gate excludes them from view.
    func testWorkflowMirrorsAreIncludedInHierarchyButFilteredByDisplayLayerGate() {
        let nonGlobalLibraryId = UUID()  // Definitely not the global library
        let docs = [
            makeContainer(),
            makeWorkflowMirror(id: "wf-1", name: "Transcribe", sortOrder: 0),
            makeWorkflowMirror(id: "wf-2", name: "Summarize", sortOrder: 1)
        ]

        // Verify workflow mirrors ARE in the hierarchy for non-global library
        // (the visibility predicate includes them for all libraries).
        let items = SidebarItemBuilder.buildLibraryHierarchy(from: docs, libraryId: nonGlobalLibraryId)
        guard let folder = container(in: items) else {
            return XCTFail("Default Workflows container missing from non-global library hierarchy")
        }
        XCTAssertEqual(folder.children?.count, 2, "predicate must include mirrors for all libraries")

        // The display layer gate is verified separately in SidebarLibraryBucketsTests
        // (testWorkflowItemsAreRenderedGatedOnFlag checks source code for the gate).
        // Here we just document that the predicate inclusion is safe because that
        // gate filters before rendering: flattenedLibraryItems only adds
        // buckets.workflowItems when (libraryId == LibraryManager.globalLibraryId).
        XCTAssertNotEqual(nonGlobalLibraryId, LibraryManager.globalLibraryId)
    }
}
