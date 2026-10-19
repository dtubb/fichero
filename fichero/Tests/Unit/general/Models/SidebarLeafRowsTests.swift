@testable import Fichero
import Foundation
import Testing

/// `read.leaf.no-chevron` (#5764): a leaf row (a page, an image, Trash, a model) is not a disclosure row.
@MainActor
struct SidebarLeafRowsTests {
    private func row(_ document: Document) -> SidebarItem {
        SidebarItem(
            id: document.id, name: document.name, icon: "doc", category: .folder, itemType: .document(document),
            children: nil, libraryId: UUID(), folderPath: "/", sortOrder: 0, isFolder: false
        )
    }

    @Test("a page or an image document is not expandable, whatever its child count says")
    func pagesAreLeaves() {
        for type in [FileType.image, .text, .other] {
            var page = Document(id: "p", docType: .file, fileType: type, name: "Page")
            page.childCount = 3
            #expect(!row(page).isExpandable, "\(type)")
        }
    }

    @Test("a folder with children is expandable, so the chevron stays for the rows that open")
    func foldersOpen() {
        var folder = Document(id: "f", docType: .folder, name: "Box")
        folder.childCount = 2
        #expect(row(folder).isExpandable)
    }

    @Test("a multi-page PDF opens; an empty folder and a childless PDF do not")
    func containersOpenOnlyWithChildren() {
        var pdf = Document(id: "d", docType: .file, fileType: .pdf, name: "Scan")
        pdf.childCount = 12
        #expect(row(pdf).isExpandable)
        pdf.childCount = 0
        #expect(!row(pdf).isExpandable)
        #expect(!row(Document(id: "e", docType: .folder, name: "Empty")).isExpandable)
    }

    @Test("the invisible chevron slot is only for a row that opens and has not fetched its children")
    func slotOnlyForOpeningRows() {
        var page = Document(id: "p", docType: .file, fileType: .image, name: "Page")
        page.childCount = 3
        #expect(!sidebarNeedsDeferredDisclosureContent(row(page)))
        var folder = Document(id: "f", docType: .folder, name: "Box")
        folder.childCount = 2
        #expect(sidebarNeedsDeferredDisclosureContent(row(folder)))
    }

    @Test("Trash and a trained model are drawn without a disclosure group")
    func nodesAreLeaves() throws {
        #expect(!(try AppSource.code("Views/Sidebar/Sections/SidebarTrashRow.swift")).contains("DisclosureGroup"))
        let models = try AppSource.code("Views/Sidebar/Sections/SidebarModelsNode.swift")
        // Only the Models node itself opens; each model inside it is a plain Label.
        #expect(models.components(separatedBy: "DisclosureGroup(").count == 2)
    }

    @Test("sidebar.top-section.order: knowledge rows, Models, Trash last")
    func nodeOrder() {
        #expect(SidebarProjectNode.order == [.knowledge, .models, .trash])
    }
}
