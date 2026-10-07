@testable import Fichero
import Testing

/// Groups are containers (#5570, spec `library-view-modes.md` §I "Groups are containers").
///
/// A group made by Group as Stack drew as a broken image ("Preview unavailable — Source file not
/// available"), was hidden from the sidebar with all its pages, and listed by name. Each test drives
/// the real content model a surface renders from: the sidebar's tree builder, the thumbnail
/// classifier, the Preview's route, the Reader's folder proxy, the columns/selection predicates and
/// the library's sort.
@MainActor
@Suite("Groups are containers (#5570)")
struct GroupsAreContainersTests {

    private let boxId = "box"
    private let groupId = "sentencia-1"

    private func group(childCount: Int = 3, sortOrder: Int = 0) -> Document {
        Document(id: groupId, parentId: boxId, docType: .group, name: "Sentencia 1", childCount: childCount, sortOrder: sortOrder)
    }

    private func page(_ id: String, sortOrder: Int, parent: String = "sentencia-1") -> Document {
        Document(id: id, parentId: parent, docType: .file, fileType: .image, name: id, sortOrder: sortOrder)
    }

    // MARK: - One predicate: a group is a navigable container

    @Test("a group is a navigable, folder-like container; a plain file is not")
    func groupIsAContainer() {
        #expect(group().isNavigableContainer)
        #expect(group().isFolderLike)
        #expect(group().isGroup)
        #expect(!page("p", sortOrder: 0).isNavigableContainer)
        #expect(!page("p", sortOrder: 0).isFolderLike)
    }

    // MARK: - Sidebar

    @Test("the sidebar shows a group, with its pages in the group's order, not by name")
    func sidebarShowsTheGroupAndItsPagesInOrder() throws {
        let box = Document(id: boxId, docType: .folder, name: "1948 Sentencias")
        let docs = [box, group(), page("leaf C", sortOrder: 0), page("leaf A", sortOrder: 1), page("leaf B", sortOrder: 2)]
        let tree = SidebarItemBuilder.buildLibraryHierarchy(from: docs, libraryId: LibraryManager.globalLibraryId)
        let boxItem = try #require(tree.first { $0.id == "doc:\(boxId)" })
        let groupItem = try #require(boxItem.children?.first { $0.id == "doc:\(groupId)" })
        #expect(groupItem.icon == DocType.group.icon)
        #expect(groupItem.children?.map(\.id) == ["doc:leaf C", "doc:leaf A", "doc:leaf B"])
    }

    @Test("an unexpanded group with pages draws a disclosure triangle")
    func unexpandedGroupIsExpandable() {
        let item = SidebarItem.fromDocument(group(childCount: 12), libraryId: LibraryManager.globalLibraryId)
        #expect(item.isExpandable)
        let empty = SidebarItem.fromDocument(group(childCount: 0), libraryId: LibraryManager.globalLibraryId)
        #expect(!empty.isExpandable)
    }

    @Test("a group's children are prefetched like a folder's")
    func groupsArePrefetched() {
        let pending = DocumentStore.containersNeedingChildren(in: [group(), page("p", sortOrder: 0)], cache: [:])
        #expect(pending.map(\.id) == [groupId])
    }

    // MARK: - Lists, table, icons

    @Test("a group's well shows a picture (its first page, served by the engine), never a folder glyph")
    func groupThumbnailIsAPicture() {
        #expect(DocumentThumbnailKind.forDocument(group()) == .storageImage)
        #expect(DocumentThumbnailKind.forDocument(group()).fetchesStorageThumbnail)
    }

    @Test("the group mark names its page count")
    func groupBadgeLabel() {
        #expect(GroupStackBadge.label(pageCount: 12) == "Group of 12 pages")
        #expect(GroupStackBadge.label(pageCount: 1) == "Group of 1 page")
    }

    @Test("a group row in the table expands")
    func tableRowExpands() {
        #expect(LibraryOutlineNode.document(group(childCount: 6), children: nil).canExpand)
    }

    // MARK: - Preview and Reader

    @Test("a selected group previews as its pages on its own canvas, not as a missing file")
    func groupPreviewsAsItsCanvas() {
        #expect(EditorView.previewRoute(for: group(), isEditing: false) == .folderContents(folderId: groupId))
        #expect(EditorView.previewRoute(for: group(), isEditing: true) == .folderContents(folderId: groupId))
    }

    @Test("the Reader reads a group as a document (the engine assembles its pages), not as a folder proxy")
    func readerDoesNotProxyAGroup() {
        #expect(ReadingPaneView.folderProxy(for: group()) == nil)
        #expect(ReadingPaneView.folderProxy(for: Document(id: "f", docType: .folder, name: "f")) != nil)
    }

    // MARK: - Order

    @Test("As Filed is the default sort, and orders by sort order then name naturally")
    func asFiledOrdersBySortOrder() {
        #expect(LibrarySortField.defaultField == .asFiled)
        #expect(LibraryToolbarState().sortField == .asFiled)
        #expect(LibrarySortField.savedSort(forFolder: "never-sorted", fieldsJSON: "{}", ascendingJSON: "{}").field == .asFiled)
        let docs = [
            page("Zeta judgment", sortOrder: 1, parent: boxId),
            page("p10", sortOrder: 3, parent: boxId),
            page("p2", sortOrder: 3, parent: boxId),
            page("p01", sortOrder: 0, parent: boxId),
        ]
        let ordered = LibrarySortField.orderedForDisplay(
            docs, field: .asFiled, using: LibrarySortField.asFiled.comparator(ascending: true)
        )
        #expect(ordered.map(\.name) == ["p01", "Zeta judgment", "p2", "p10"])
        let descending = LibrarySortField.orderedForDisplay(
            docs, field: .asFiled, using: LibrarySortField.asFiled.comparator(ascending: false)
        )
        #expect(descending.map(\.name) == ["p10", "p2", "Zeta judgment", "p01"])
    }

    @Test("As Filed round-trips through the table's key-path bridge and offers no column comparator")
    func asFiledBridges() {
        let keyPath = LibrarySortField.asFiled.comparator(ascending: true)[0].keyPath
        #expect(LibrarySortField.field(forDocumentKeyPath: keyPath) == .asFiled)
        #expect(LibrarySortField.asFiled.outlineColumnComparator(ascending: true) == nil)
        #expect(LibrarySortField.fields(isSearching: false).contains(.asFiled))
        #expect(LibrarySortField.asFiled.serverSortBy == nil)
    }
}
