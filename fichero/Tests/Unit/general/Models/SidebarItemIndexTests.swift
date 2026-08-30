@testable import Fichero
import Foundation
import XCTest

/// #4228 follow-up — the id→row index that replaced the recursive tree walk on
/// the sidebar click path.
///
/// Resolving "which item is this id?" used to be `findItemById`, a DFS over the
/// entire cached forest. A single click ran at least four of them — routing the
/// selection, `hasSelection` for the bottom toolbar, `selectedItem` for the
/// focused-values config, and one per highlighted row for `selectedItems` — and
/// all of those are computed properties, so they recomputed on every body pass
/// of `SidebarView`, not once per click.
///
/// These tests pin two things: that the index answers exactly what the walk
/// answered (including the duplicate-id case, which is real — a workflow is
/// mirrored into a same-id document node, #4186), and that it actually SCALES,
/// measured against the walk it replaced on a 10,000-row fixture.
@MainActor
final class SidebarItemIndexTests: XCTestCase {

    private let libraryId = UUID()

    private func doc(id: String, name: String, parentId: String? = nil, isFolder: Bool = false) -> Document {
        Document(
            id: id,
            parentId: parentId,
            docType: isFolder ? .folder : .file,
            name: name,
            sortOrder: 0
        )
    }

    private func item(id: String, name: String, children: [SidebarItem]? = nil) -> SidebarItem {
        SidebarItem(
            id: id,
            name: name,
            icon: "folder",
            category: .folder,
            itemType: .folder(folderPath: "/\(name)"),
            children: children,
            libraryId: libraryId,
            folderPath: "/\(name)",
            sortOrder: 0,
            isFolder: true
        )
    }

    // MARK: - Same answers as the walk it replaced

    func testFindsTopLevelItem() {
        let index = sidebarItemIndex([item(id: "a", name: "A"), item(id: "b", name: "B")])
        XCTAssertEqual(index["b"]?.name, "B")
    }

    func testFindsDeeplyNestedItem() {
        let forest = [
            item(id: "a", name: "A", children: [
                item(id: "a1", name: "A1", children: [
                    item(id: "a2", name: "A2")
                ])
            ])
        ]
        XCTAssertEqual(sidebarItemIndex(forest)["a2"]?.name, "A2")
    }

    func testMissingIdIsNil() {
        XCTAssertNil(sidebarItemIndex([item(id: "a", name: "A")])["nope"])
    }

    func testEmptyForestIndexesToNothing() {
        XCTAssertTrue(sidebarItemIndex([]).isEmpty)
    }

    /// The forest does NOT guarantee unique ids — the engine mirrors workflows
    /// into same-id document nodes (#4186), so the same id can appear twice.
    /// `findItemById` returns the FIRST hit in DFS pre-order; a last-wins index
    /// would silently reroute those clicks to the other row, which is a
    /// behaviour change disguised as an optimisation.
    func testDuplicateIdKeepsFirstInDFSPreorder() {
        let forest = [
            item(id: "root", name: "Root", children: [item(id: "dup", name: "First")]),
            item(id: "dup", name: "Second")
        ]
        let index = sidebarItemIndex(forest)
        XCTAssertEqual(index["dup"]?.name, "First")
        XCTAssertEqual(
            index["dup"]?.name,
            findSidebarItemById("dup", in: forest)?.name,
            "the index must resolve duplicates exactly as the walk did"
        )
    }

    /// Agreement with the walk across a whole realistic tree, not just the
    /// hand-picked cases above.
    func testAgreesWithTheWalkForEveryIdInARealTree() {
        let forest = SidebarItemBuilder.buildLibraryHierarchy(
            from: hierarchyFixture(folders: 20, childrenPerFolder: 10),
            libraryId: libraryId
        )
        let index = sidebarItemIndex(forest)
        XCTAssertFalse(index.isEmpty)
        for id in index.keys {
            XCTAssertEqual(
                index[id]?.id,
                findSidebarItemById(id, in: forest)?.id,
                "index and walk disagree for \(id)"
            )
        }
    }

    // MARK: - Scaling (the reason the index exists)

    /// N = 10,000 rows. The walk is O(rows) per lookup; the index is O(1) after
    /// one O(rows) build. The assertion is a RATIO rather than an absolute
    /// budget so it means the same thing on a loaded CI box as on an idle one —
    /// an absolute millisecond threshold on this machine is a flake generator
    /// (see the swap-pressure note in the ops docs).
    func testIndexedLookupScalesWhereTheWalkDoesNot() {
        let documents = hierarchyFixture(folders: 100, childrenPerFolder: 100)
        XCTAssertEqual(documents.count, 10_100)

        let forest = SidebarItemBuilder.buildLibraryHierarchy(from: documents, libraryId: libraryId)
        let index = sidebarItemIndex(forest)
        XCTAssertGreaterThanOrEqual(index.count, 10_000, "every row must be indexed")

        // Deep, late ids — the worst case for a DFS and the realistic one for a
        // click on a row near the bottom of a large library. 200 probes across
        // the LAST TWO folders: the fixture has 100 children per folder, so a
        // single-folder 0..<200 range probes 100 ids that don't exist.
        let probes = (0..<100).flatMap { ["doc:folder-98-child-\($0)", "doc:folder-99-child-\($0)"] }
        for probe in probes {
            XCTAssertNotNil(index[probe], "fixture id \(probe) must exist")
        }

        let walkStart = DispatchTime.now()
        for probe in probes {
            _ = findSidebarItemById(probe, in: forest)
        }
        let walkNs = DispatchTime.now().uptimeNanoseconds - walkStart.uptimeNanoseconds

        let indexStart = DispatchTime.now()
        for probe in probes {
            _ = index[probe]
        }
        let indexNs = DispatchTime.now().uptimeNanoseconds - indexStart.uptimeNanoseconds

        XCTAssertGreaterThan(
            Double(walkNs),
            Double(indexNs) * 10,
            """
            200 lookups over a 10k-row sidebar: walk \(walkNs / 1_000)µs vs \
            index \(indexNs / 1_000)µs. The index must be at least 10× cheaper; \
            it is not, so the click path is walking the tree again.
            """
        )
    }

    /// The build itself must be one pass, not a walk per row — an accidental
    /// `findItemById` inside the indexer would make the whole change a
    /// pessimisation and every other test here would still pass.
    func testIndexBuildIsLinearNotQuadratic() {
        let small = SidebarItemBuilder.buildLibraryHierarchy(
            from: hierarchyFixture(folders: 10, childrenPerFolder: 100),
            libraryId: libraryId
        )
        let large = SidebarItemBuilder.buildLibraryHierarchy(
            from: hierarchyFixture(folders: 100, childrenPerFolder: 100),
            libraryId: libraryId
        )

        let smallNs = elapsedNs { _ = sidebarItemIndex(small) }
        let largeNs = elapsedNs { _ = sidebarItemIndex(large) }

        // 10× the rows must not cost anywhere near 100× the time. The bound is
        // deliberately loose (30×) — it catches a quadratic, not a constant factor.
        XCTAssertLessThan(
            Double(largeNs),
            Double(max(smallNs, 1)) * 30,
            "index build looks super-linear: \(smallNs / 1_000)µs at 1k rows vs \(largeNs / 1_000)µs at 10k"
        )
    }

    // MARK: - Fixtures

    private func elapsedNs(_ body: () -> Void) -> UInt64 {
        let start = DispatchTime.now()
        body()
        return DispatchTime.now().uptimeNanoseconds - start.uptimeNanoseconds
    }

    /// `folders` root folders, each holding `childrenPerFolder` sub-folders.
    ///
    /// Every node is a folder because `SidebarItemBuilder.isSidebarVisible`
    /// drops plain files — a fixture of files would build an empty tree and the
    /// scaling assertion would pass by measuring nothing.
    private func hierarchyFixture(folders: Int, childrenPerFolder: Int) -> [Document] {
        var documents: [Document] = []
        documents.reserveCapacity(folders * (childrenPerFolder + 1))
        for folderIndex in 0..<folders {
            let folderId = "folder-\(folderIndex)"
            documents.append(doc(id: folderId, name: "Folder \(folderIndex)", isFolder: true))
            for childIndex in 0..<childrenPerFolder {
                documents.append(
                    doc(
                        id: "\(folderId)-child-\(childIndex)",
                        name: "Child \(childIndex)",
                        parentId: folderId,
                        isFolder: true
                    )
                )
            }
        }
        return documents
    }
}
