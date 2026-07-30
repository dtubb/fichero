@testable import Fichero
import XCTest

/// #4300 — a folder of imported Markdown files would not expand in the
/// sidebar.
///
/// Import was fine: the server maps `.md` → `FileType.text` (`ingest.py`
/// `_FILE_TYPE_MAP`) and creates the child rows. The display side dropped
/// them: `SidebarItemBuilder.isSidebarVisible` excluded generic `.file`
/// docs, and because the predicate runs BEFORE the parent→children map is
/// built, the folder's `children` came out nil → `isExpandable == false`
/// → no chevron, nothing to expand.
@MainActor
final class SidebarMarkdownFolderTests: XCTestCase {

    private static let folderId = "notes-folder"

    private func makeFolder() -> Document {
        Document(id: Self.folderId, parentId: nil, docType: .folder, name: "Notes", childCount: 0)
    }

    private func makeMarkdownDoc(id: String, name: String, sortOrder: Int = 0) -> Document {
        Document(
            id: id,
            parentId: Self.folderId,
            docType: .file,
            fileType: .text,
            name: name,
            sortOrder: sortOrder
        )
    }

    private func folder(in items: [SidebarItem]) -> SidebarItem? {
        items.first { $0.id == "doc:\(Self.folderId)" }
    }

    /// The direct repro: folder + markdown children build into an expandable
    /// row whose children are the markdown files.
    func testMarkdownFilesRenderAsFolderChildren() {
        let docs = [
            makeFolder(),
            makeMarkdownDoc(id: "md-1", name: "alpha.md", sortOrder: 0),
            makeMarkdownDoc(id: "md-2", name: "beta.md", sortOrder: 1)
        ]
        let items = SidebarItemBuilder.buildLibraryHierarchy(from: docs, libraryId: UUID())

        guard let notes = folder(in: items) else {
            return XCTFail("Notes folder missing from the tree")
        }
        XCTAssertEqual(notes.children?.map(\.name), ["alpha.md", "beta.md"])
        XCTAssertTrue(notes.isExpandable, "folder of markdown files must show a chevron and expand")
    }

    /// The predicate itself: text files are sidebar-visible.
    func testMarkdownDocIsSidebarVisible() {
        XCTAssertTrue(SidebarItemBuilder.isSidebarVisible(makeMarkdownDoc(id: "md-1", name: "alpha.md")))
    }

    /// Other generic leaf files (docx/word, unknown) are visible too — one
    /// Finder rule for every leaf, no per-extension surprises.
    func testOtherGenericFilesAreSidebarVisible() {
        let word = Document(parentId: Self.folderId, docType: .file, fileType: .word, name: "draft.docx")
        let other = Document(parentId: Self.folderId, docType: .file, fileType: .other, name: "data.bin")
        XCTAssertTrue(SidebarItemBuilder.isSidebarVisible(word))
        XCTAssertTrue(SidebarItemBuilder.isSidebarVisible(other))
    }

    /// Chunks stay out — text fragments are not user-facing tree nodes.
    func testChunksRemainHidden() {
        let chunk = Document(parentId: Self.folderId, docType: .chunk, name: "fragment")
        XCTAssertFalse(SidebarItemBuilder.isSidebarVisible(chunk))
    }

    /// Markdown children respect the shared sibling order (sortOrder → name).
    func testMarkdownChildrenSortLikeAnyOtherSibling() {
        let docs = [
            makeFolder(),
            makeMarkdownDoc(id: "md-z", name: "zulu.md", sortOrder: 0),
            makeMarkdownDoc(id: "md-a", name: "alpha.md", sortOrder: 0)
        ]
        let items = SidebarItemBuilder.buildLibraryHierarchy(from: docs, libraryId: UUID())
        XCTAssertEqual(folder(in: items)?.children?.map(\.name), ["alpha.md", "zulu.md"])
    }
}
