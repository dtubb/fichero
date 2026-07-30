@testable import Fichero
import XCTest

/// #4419: nothing inside the Marshall folder could be run, and a
/// multi-selection collapsed to one row.
///
/// Three of the assertions in this file used to encode the BUG as the contract
/// — a foreign-library file "excluded", an unloaded folder resolving to
/// nothing, an empty folder resolving to nothing. Those are the exact
/// behaviours that produced "nothing in Marshall can be run", so they are
/// inverted here rather than preserved. The page-granularity cases (#4298) are
/// untouched: they were right and they still are.
final class WorkflowRunTargetResolverTests: XCTestCase {
    private let documents = [
        Document(id: "a", parentId: "/letters", name: "A"),
        Document(id: "b", parentId: "/letters", name: "B"),
        Document(id: "nested", parentId: "/letters/nested", name: "Nested"),
        Document(id: "outside", parentId: "/outside", name: "Outside"),
        Document(id: "folder", parentId: "/letters", docType: .folder, name: "Folder")
    ]

    private func targets(
        clicked: WorkflowRunTarget,
        selection: Set<WorkflowRunTarget> = [],
        documents: [Document]
    ) -> [String] {
        WorkflowRunTargetResolver.resolve(
            clicked: clicked, selection: selection, documents: documents
        ).targetIds
    }

    // MARK: - The Marshall case: a row always resolves to something

    /// The defect, stated directly. A file in a library whose store this view
    /// does not hold used to fail a `documents.contains` presence test and
    /// resolve to nothing, which emptied the target list and made the whole
    /// submenu vanish for the subtree.
    func testForeignLibraryFileResolvesToItself() {
        let resolution = WorkflowRunTargetResolver.resolve(
            clicked: .file("marshall-doc"),
            selection: [],
            documents: documents
        )
        XCTAssertEqual(resolution.targetIds, ["marshall-doc"])
        XCTAssertFalse(resolution.isEmpty, "a clicked row must never resolve to nothing")
    }

    /// The whole-store version: even with NO documents loaded at all, a clicked
    /// file runs. Resolution must not depend on which client collection happens
    /// to be populated.
    func testFileResolvesWithAnEmptyDocumentStore() {
        XCTAssertEqual(targets(clicked: .file("a"), documents: []), ["a"])
    }

    /// A selection spanning libraries keeps every member. The old resolver
    /// dropped the foreign one silently — the narrowing half of #4419.
    func testForeignSelectionMembersAreKept() {
        XCTAssertEqual(
            targets(
                clicked: .file("a"),
                selection: [.file("a"), .file("foreign-library-document")],
                documents: documents
            ),
            ["a", "foreign-library-document"]
        )
    }

    /// A folder whose children have not loaded resolves to the folder itself,
    /// flagged, so the engine expands it. It used to resolve to nothing.
    func testUnloadedFolderResolvesToItselfAndSaysSo() {
        let parentViewDocuments = [Document(id: "/archive", docType: .folder, name: "Archive")]
        let resolution = WorkflowRunTargetResolver.resolve(
            clicked: .folder("/archive/letters"),
            selection: [],
            documents: parentViewDocuments
        )
        XCTAssertEqual(resolution.targetIds, ["/archive/letters"])
        XCTAssertTrue(resolution.usedRowIdentityFallback)
    }

    func testLoadedFolderResolvesItsChildren() {
        let loaded = [
            Document(id: "/archive", docType: .folder, name: "Archive"),
            Document(id: "letter", parentId: "/archive/letters", name: "Letter")
        ]
        XCTAssertEqual(targets(clicked: .folder("/archive/letters"), documents: loaded), ["letter"])
    }

    func testEmptyFolderResolvesToItselfRatherThanNothing() {
        let resolution = WorkflowRunTargetResolver.resolve(
            clicked: .folder("/empty"), selection: [], documents: documents
        )
        XCTAssertEqual(resolution.targetIds, ["/empty"])
        XCTAssertFalse(resolution.isEmpty)
    }

    // MARK: - Folders resolve to ALL descendants, at any depth

    /// #4399's box → archive → folder hierarchy. The old resolver matched
    /// `$0.parentId == path` — direct children only — so a run on the box
    /// reached only the files sitting loose at its top.
    func testFolderResolvesDescendantsAtEveryDepth() {
        let deep = [
            Document(id: "box", docType: .folder, name: "Box"),
            Document(id: "loose", parentId: "box", name: "Loose"),
            Document(id: "archive", parentId: "box", docType: .folder, name: "Archive"),
            Document(id: "inArchive", parentId: "archive", name: "In Archive"),
            Document(id: "folder", parentId: "archive", docType: .folder, name: "Folder"),
            Document(id: "deepest", parentId: "folder", name: "Deepest"),
            Document(id: "elsewhere", parentId: "other", name: "Elsewhere")
        ]
        let resolved = targets(clicked: .folder("box"), documents: deep)
        XCTAssertEqual(Set(resolved), ["loose", "inArchive", "deepest"])
        XCTAssertFalse(resolved.contains("elsewhere"))
        // Folders themselves are not run targets — their files are.
        XCTAssertFalse(resolved.contains("archive"))
        XCTAssertFalse(resolved.contains("folder"))
    }

    /// A malformed parent cycle must not hang the menu.
    func testCyclicParentsTerminate() {
        let cyclic = [
            Document(id: "x", parentId: "y", docType: .folder, name: "X"),
            Document(id: "y", parentId: "x", docType: .folder, name: "Y"),
            Document(id: "file", parentId: "x", name: "File")
        ]
        XCTAssertEqual(targets(clicked: .folder("x"), documents: cyclic), ["file"])
    }

    func testDirectChildrenStillResolve() {
        XCTAssertEqual(targets(clicked: .folder("/letters"), documents: documents), ["a", "b"])
    }

    /// `nested` hangs off `/letters/nested`, which is not any document's id, so
    /// it is not a descendant of `/letters` — unreachable, not excluded.
    func testUnparentedDocumentIsNotADescendant() {
        XCTAssertFalse(targets(clicked: .folder("/letters"), documents: documents).contains("nested"))
    }

    // MARK: - Selection: honoured, or the narrowing is declared

    func testClickInsideSelectionRunsTheWholeSelection() {
        let resolution = WorkflowRunTargetResolver.resolve(
            clicked: .file("b"),
            selection: [.file("a"), .file("b")],
            documents: documents
        )
        XCTAssertEqual(resolution.targetIds, ["a", "b"])
        XCTAssertFalse(resolution.ignoredSelection)
    }

    /// When the clicked row is OUTSIDE the selection the run targets the
    /// clicked row — but it must SAY so. Silently discarding a selection is the
    /// same defect class as silently widening one (#4396).
    func testClickOutsideSelectionNarrowsAndDeclaresIt() {
        let resolution = WorkflowRunTargetResolver.resolve(
            clicked: .folder("/letters"),
            selection: [.file("outside")],
            documents: documents
        )
        XCTAssertEqual(resolution.targetIds, ["a", "b"])
        XCTAssertTrue(resolution.ignoredSelection, "the discarded selection must be declared")
    }

    /// No selection at all is not a narrowing — there is nothing to discard.
    func testNoSelectionIsNotReportedAsIgnored() {
        let resolution = WorkflowRunTargetResolver.resolve(
            clicked: .file("a"), selection: [], documents: documents
        )
        XCTAssertFalse(resolution.ignoredSelection)
    }

    func testSelectedFileAndFolderUnionIsDeduplicated() {
        XCTAssertEqual(
            targets(
                clicked: .folder("/letters"),
                selection: [.file("a"), .folder("/letters")],
                documents: documents
            ),
            ["a", "b"]
        )
    }

    /// `selection` is a `Set`, so order must come from somewhere deterministic
    /// or the same gesture sends a differently-ordered request each time.
    func testOrderIsDeterministicAcrossRepeatedResolution() {
        let selection: Set<WorkflowRunTarget> = [.file("b"), .file("a"), .file("unknown-1"), .file("unknown-2")]
        let first = targets(clicked: .file("a"), selection: selection, documents: documents)
        for _ in 0..<50 {
            XCTAssertEqual(targets(clicked: .file("a"), selection: selection, documents: documents), first)
        }
        // Known documents keep visual order; unknown ones sort stably after.
        XCTAssertEqual(first, ["a", "b", "unknown-1", "unknown-2"])
    }

    // MARK: - PDF page rows (#4298) — unchanged, and still right

    private var documentsWithPDFPages: [Document] {
        documents + [
            Document(id: "pdf", parentId: "/letters", name: "Scan.pdf"),
            Document(id: "pdf-page-2", parentId: "pdf", docType: .page, name: "Scan.pdf - Page 2"),
            Document(id: "pdf-page-3", parentId: "pdf", docType: .page, name: "Scan.pdf - Page 3")
        ]
    }

    /// A page row resolves to EXACTLY that page — never the parent PDF, which
    /// the server would fan out to every page, multiplying provider spend.
    func testPageRowResolvesToThatPageOnly() {
        XCTAssertEqual(
            targets(clicked: .file("pdf-page-2"), documents: documentsWithPDFPages),
            ["pdf-page-2"]
        )
    }

    func testPageRowDoesNotWidenToParentOrSiblingPages() {
        let resolved = targets(
            clicked: .file("pdf-page-2"),
            selection: [.file("pdf-page-2")],
            documents: documentsWithPDFPages
        )
        XCTAssertEqual(resolved, ["pdf-page-2"])
        XCTAssertFalse(resolved.contains("pdf"))
        XCTAssertFalse(resolved.contains("pdf-page-3"))
    }

    /// A whole-document run stays the parent's id — the SERVER owns the
    /// per-page fan-out. Note this is a `.file` target, so descendant expansion
    /// never applies to it.
    func testParentPDFRowResolvesToTheParentNotItsPages() {
        XCTAssertEqual(targets(clicked: .file("pdf"), documents: documentsWithPDFPages), ["pdf"])
    }

    // MARK: - The invariant

    /// Whatever the inputs, a clicked row yields at least one target. This is
    /// the property that makes the submenu impossible to lose.
    func testAClickedRowAlwaysYieldsATarget() {
        let clicks: [WorkflowRunTarget] = [
            .file("a"), .file("unknown"), .folder("/letters"), .folder("/empty"), .folder("unknown")
        ]
        let selections: [Set<WorkflowRunTarget>] = [[], [.file("a")], [.file("outside")], [.folder("/letters")]]
        let stores: [[Document]] = [documents, [], documentsWithPDFPages]
        for clicked in clicks {
            for selection in selections {
                for store in stores {
                    let resolution = WorkflowRunTargetResolver.resolve(
                        clicked: clicked, selection: selection, documents: store
                    )
                    XCTAssertFalse(
                        resolution.isEmpty,
                        "clicked \(clicked) with \(selection.count) selected and \(store.count) docs"
                    )
                }
            }
        }
    }
}
