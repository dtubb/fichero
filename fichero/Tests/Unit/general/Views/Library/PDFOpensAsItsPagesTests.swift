@testable import Fichero
import Testing

/// A PDF opens as its pages, as a group does (`library.pdf.opens-as-its-pages`, #6410).
@MainActor
struct PDFOpensAsItsPagesTests {
    private func pdf(childCount: Int) -> Document {
        Document(id: "deed", parentId: "box3", docType: .file, fileType: .pdf, name: "The deed.pdf", childCount: childCount)
    }

    @Test func aPDFWithPagesPreviewsAsItsPagesLikeAGroup() {
        #expect(EditorView.previewRoute(for: pdf(childCount: 12), isEditing: false) == .folderContents(folderId: "deed"))
        let group = Document(id: "g", parentId: "box3", docType: .group, name: "G", childCount: 3)
        #expect(EditorView.previewRoute(for: group, isEditing: false) == .folderContents(folderId: "g"))
    }

    @Test func aPDFWhosePagesAreNotListedYetStillShowsTheFile() {
        #expect(EditorView.previewRoute(for: pdf(childCount: 0), isEditing: false) == .storageDisplay(documentId: "deed"))
    }

    @Test func aPDFIsANavigableContainerTheSidebarAndColumnsOpen() {
        #expect(pdf(childCount: 12).isNavigableContainer)
        #expect(SidebarItem.fromDocument(pdf(childCount: 12), libraryId: LibraryManager.globalLibraryId).isExpandable)
    }

    @Test func aPDFsPagesDrawInThePanesViewButAGroupKeepsItsBoard() {
        #expect(EditorView.foldersPaneView(for: pdf(childCount: 12)))
        let group = Document(id: "g", parentId: "box3", docType: .group, name: "G", childCount: 3)
        #expect(!EditorView.foldersPaneView(for: group))
    }

    @Test func columnsOpenTheNextColumnForAPDFAndAGroupNotAPlainFile() {
        let group = Document(id: "g", parentId: "box3", docType: .group, name: "G", childCount: 3)
        let note = Document(id: "n", parentId: "box3", docType: .file, fileType: .text, name: "n.txt")
        #expect(LibraryView.columnOpensChildren(pdf(childCount: 12)))
        #expect(LibraryView.columnOpensChildren(group))
        #expect(!LibraryView.columnOpensChildren(note))
    }

    /// A double-clicked page row reaches the window's selection hook (`library.contents.double-click-selects-the-item`).
    @Test func aDoubleClickedPageRowIsHandedToTheWindowsSelection() {
        var handed: [String] = []
        let page = Document(id: "p4", parentId: "deed", docType: .page, name: "4")
        LibraryView.handOffOpenedItem(page) { handed.append($0.id) }
        LibraryView.handOffOpenedItem(page, to: nil)
        #expect(handed == ["p4"])
    }
}
