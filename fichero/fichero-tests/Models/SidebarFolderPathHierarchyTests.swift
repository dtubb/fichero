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

    /// BUG (#see report): `buildHierarchyFromPath` walks down from "/", and
    /// `createFolderItems` bails on a path with no components. A saved search
    /// (or chat, or workflow) whose `folder_path` is the EMPTY STRING therefore
    /// has no folder created for it and is never visited by `buildSubtree` — it
    /// is silently absent from the sidebar. `folder_path` is a plain server
    /// string with no client-side normalisation, so "" is one bad write away.
    func testAnItemWithAnEmptyFolderPathMustStillRender() {
        let items = SidebarItemBuilder.buildSearchHierarchy(
            from: [search("Orphan", folderPath: "")], libraryId: libraryId
        )
        XCTExpectFailure(
            "BUG: an empty folder_path produces no folder and is never walked, "
            + "so the row vanishes from the sidebar with no error."
        ) {
            XCTAssertEqual(flatten(items), ["Orphan"])
        }
    }

    /// BUG (#see report): the folder path is used as a raw dictionary key, so
    /// "/archive" and "/archive/" are two different folders with two different
    /// `SidebarItem.folder` ids — and both resolve to the same parent, so the
    /// user sees the SAME folder listed twice with its contents split between
    /// them. `parentFolderPath` already normalises the trailing slash away when
    /// it computes a parent, so the two spellings are known to be equivalent
    /// one line later.
    func testATrailingSlashMustNotDuplicateTheFolder() {
        let items = SidebarItemBuilder.buildSearchHierarchy(
            from: [
                search("A", folderPath: "/archive"),
                search("B", folderPath: "/archive/")
            ],
            libraryId: libraryId
        )
        XCTExpectFailure(
            "BUG: '/archive' and '/archive/' are distinct keys, so one folder "
            + "renders as two rows with its contents split between them."
        ) {
            XCTAssertEqual(items.count, 1, "one folder, however its path was spelled")
            XCTAssertEqual(Set(flatten(items)), ["archive", "A", "B"])
        }
    }

    /// BUG (#see report): sibling FOLDERS are ordered with `$0.name < $1.name`
    /// — a raw unicode-scalar compare — while sibling DOCUMENTS use
    /// `localizedCaseInsensitiveCompare` (`childOrder`). So in the searches and
    /// chats sections every lowercase folder sorts after every uppercase one
    /// ("Zebra" before "apple"), and the same two names order differently
    /// depending on which section they are in.
    func testFolderSiblingsSortLikeDocumentSiblings() {
        let items = SidebarItemBuilder.buildSearchHierarchy(
            from: [
                search("x", folderPath: "/apple"),
                search("y", folderPath: "/Zebra")
            ],
            libraryId: libraryId
        )
        XCTExpectFailure(
            "BUG: folder siblings use a raw `<` on name, not the "
            + "localizedCaseInsensitiveCompare every document row uses, so "
            + "case decides the order."
        ) {
            XCTAssertEqual(names(items), ["apple", "Zebra"])
        }
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
