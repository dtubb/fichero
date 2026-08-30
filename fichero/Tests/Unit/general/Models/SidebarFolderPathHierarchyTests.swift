import Foundation
import XCTest

@testable import Fichero

/// The folder-path hierarchy every non-document sidebar section shares —
/// saved searches, chats, workflows and chains all walk
/// `SidebarItemBuilder.buildHierarchyFromPath`. Split out of
/// `SidebarBuilderInboxAndPathTests` to stay inside the lint budget.
///
/// This walker is where a row can VANISH rather than render wrong: it starts
/// at "/" and only visits what `createFolderItems` managed to materialise.
@MainActor
final class SidebarFolderPathHierarchyTests: XCTestCase {

    private let libraryId = UUID()

    private func names(_ items: [SidebarItem]) -> [String] { items.map(\.name) }

    // MARK: - The shared folder-path hierarchy

    private func search(_ name: String, folderPath: String, sortOrder: Int = 0) -> SavedSearch {
        SavedSearch(id: name, name: name, folderPath: folderPath, sortOrder: sortOrder)
    }

    private func flatten(_ items: [SidebarItem]) -> [String] {
        items.flatMap { [$0.name] + flatten($0.children ?? []) }
    }

    func testRootLevelItemsRenderDirectly() {
        let items = SidebarItemBuilder.buildSearchHierarchy(
            from: [search("Diaries", folderPath: "/")], libraryId: libraryId
        )
        XCTAssertEqual(names(items), ["Diaries"])
    }

    /// A nested path materialises every intermediate folder, not just the leaf.
    func testEveryIntermediateFolderIsMaterialised() {
        let items = SidebarItemBuilder.buildSearchHierarchy(
            from: [search("Letters", folderPath: "/archive/1859/letters")],
            libraryId: libraryId
        )
        XCTAssertEqual(flatten(items), ["archive", "1859", "letters", "Letters"])
    }

    /// FIXED (#4528): paths are normalised before grouping, so an EMPTY
    /// `folder_path` — one bad server write away, since it is a plain string —
    /// lands on "/" and renders at the root instead of silently vanishing
    /// (the walker starts at "/" and only visits materialised folders).
    func testAnItemWithAnEmptyFolderPathMustStillRender() {
        let items = SidebarItemBuilder.buildSearchHierarchy(
            from: [search("Orphan", folderPath: "")], libraryId: libraryId
        )
        XCTAssertEqual(flatten(items), ["Orphan"])
    }

    /// FIXED (#4528): "/archive" and "/archive/" normalise to one dictionary
    /// key (component split/rejoin — the same logic `parentFolderPath` always
    /// used), so one folder renders once with all its contents.
    func testATrailingSlashMustNotDuplicateTheFolder() {
        let items = SidebarItemBuilder.buildSearchHierarchy(
            from: [
                search("A", folderPath: "/archive"),
                search("B", folderPath: "/archive/")
            ],
            libraryId: libraryId
        )
        XCTAssertEqual(items.count, 1, "one folder, however its path was spelled")
        XCTAssertEqual(Set(flatten(items)), ["archive", "A", "B"])
    }

    /// FIXED (#4528): sibling folders now order by the same
    /// `localizedCaseInsensitiveCompare` sibling documents use (`childOrder`'s
    /// name rung), so case no longer decides the order and the same two names
    /// order identically in every section.
    func testFolderSiblingsSortLikeDocumentSiblings() {
        let items = SidebarItemBuilder.buildSearchHierarchy(
            from: [
                search("x", folderPath: "/apple"),
                search("y", folderPath: "/Zebra")
            ],
            libraryId: libraryId
        )
        XCTAssertEqual(names(items), ["apple", "Zebra"])
    }

    /// Items inside a folder are ordered by `sortOrder`, and that ordering must
    /// survive the recursion into a nested folder.
    func testItemsInsideAFolderKeepTheirSortOrder() {
        let items = SidebarItemBuilder.buildSearchHierarchy(
            from: [
                search("third", folderPath: "/archive", sortOrder: 3),
                search("first", folderPath: "/archive", sortOrder: 1),
                search("second", folderPath: "/archive", sortOrder: 2)
            ],
            libraryId: libraryId
        )
        XCTAssertEqual(flatten(items), ["archive", "first", "second", "third"])
    }

    /// A folder that contains only OTHER folders still renders — the recursion
    /// must not prune a branch just because it holds no leaf of its own.
    func testAFolderHoldingOnlyFoldersStillRenders() {
        let items = SidebarItemBuilder.buildSearchHierarchy(
            from: [search("Deep", folderPath: "/a/b/c")], libraryId: libraryId
        )
        XCTAssertEqual(flatten(items), ["a", "b", "c", "Deep"])
    }

    /// Two items in the same deep folder share ONE chain of folder rows rather
    /// than each materialising its own.
    func testItemsSharingAPathShareOneFolderChain() {
        let items = SidebarItemBuilder.buildSearchHierarchy(
            from: [
                search("A", folderPath: "/a/b"),
                search("B", folderPath: "/a/b")
            ],
            libraryId: libraryId
        )
        XCTAssertEqual(items.count, 1)
        XCTAssertEqual(flatten(items), ["a", "b", "A", "B"])
    }

    /// An empty input set produces an empty tree, not a phantom root folder.
    func testNoItemsProduceNoRows() {
        XCTAssertTrue(
            SidebarItemBuilder.buildSearchHierarchy(from: [], libraryId: libraryId).isEmpty
        )
    }

    /// Chats go through the SAME builder, so the path rules cannot diverge
    /// between sections. Checked with the other section's entry point so a
    /// future per-section copy of the walker fails here.
    func testChatsUseTheSamePathRulesAsSearches() {
        let conversation = Conversation(
            id: "c1", title: "Notes", folderPath: "/archive/1859", sortOrder: 0
        )
        let items = SidebarItemBuilder.buildChatHierarchy(
            from: [conversation], libraryId: libraryId
        )
        XCTAssertEqual(flatten(items), ["archive", "1859", "Notes"])
    }
}
