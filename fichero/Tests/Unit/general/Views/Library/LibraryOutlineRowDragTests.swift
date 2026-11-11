@testable import Fichero
import Foundation
import Testing

// Spec: library.table.every-column-selects (#6538), ui/library-view-modes.md.
//
// A click anywhere in a table row selects it, the Name column included. The Name column
// stopped selecting because its cell carried the row's drag (`.draggable`), and a drag source
// inside an NSTableView cell takes the mouse-down before the table sees it. The drag is now
// the ROW's (`LibraryItemDrag.forOutlineRow`, delivered through `TableRowContent.itemProvider`).

@Suite("Library table: the row drags, so every column selects (#6538)")
struct LibraryOutlineRowDragTests {

    private let libraryId = UUID()

    private func folder() -> Document {
        Document(id: "d1", docType: .folder, name: "Letters")
    }

    private func page() -> Document {
        Document(id: "p3", parentId: "d1", docType: .page, name: "upload-tmp.png", sequence: 3)
    }

    private func artifact(content: String?) -> Artifact {
        Artifact(id: "a1", documentId: "d1", sourceArtifactId: nil,
                 version: 1, artifactType: "transcript", content: content,
                 data: nil, runId: nil, provider: nil, model: nil,
                 stepName: "transcript", confidence: nil,
                 reviewed: false, createdAt: Date())
    }

    @Test("a document row drags as that document, the same payload as list and icon rows")
    func documentRowDragsTheDocument() throws {
        let drag = try #require(LibraryItemDrag.forOutlineRow(.document(folder(), children: nil), libraryId: libraryId))
        #expect(drag == LibraryItemDrag.forDocument(folder(), libraryId: libraryId))
        #expect(drag.libraryId == libraryId)
        #expect(drag.exportsSourceFile)
    }

    @Test("a page row drags as that page, not as its parent")
    func pageRowDragsThePage() throws {
        let node = LibraryOutlineNode.pageItem(page(), parent: folder())
        let drag = try #require(LibraryItemDrag.forOutlineRow(node, libraryId: libraryId))
        #expect(drag.kind == .page)
        #expect(drag.id == "p3")
        #expect(drag.pageIndex == 2)
    }

    @Test("a child-group row drags as a group naming its document")
    func groupRowDragsTheGroup() throws {
        let node = LibraryOutlineNode.childGroup(.pages, document: folder(), count: 12)
        let drag = try #require(LibraryItemDrag.forOutlineRow(node, libraryId: libraryId))
        #expect(drag.kind == .group)
        #expect(drag.id == node.id)
        #expect(drag.documentId == "d1")
        #expect(drag.text == "12 pages")
    }

    @Test("an artifact row drags its text, or its type name when it has none")
    func artifactRowDragsItsText() throws {
        let withText = LibraryOutlineNode.artifactItem(artifact(content: "Muy señor mío"), parent: folder())
        let empty = LibraryOutlineNode.artifactItem(artifact(content: ""), parent: folder())
        let textDrag = try #require(LibraryItemDrag.forOutlineRow(withText, libraryId: libraryId))
        let emptyDrag = try #require(LibraryItemDrag.forOutlineRow(empty, libraryId: libraryId))
        #expect(textDrag.kind == .artifact)
        #expect(textDrag.documentId == "d1")
        #expect(textDrag.text == "Muy señor mío")
        #expect(emptyDrag.text == artifact(content: "").artifactTypeDisplayName)
        #expect(!textDrag.exportsSourceFile)
    }

    /// Absence check (the failing-first one): before #6538 the Name column's cells carried
    /// `.draggable`, and that is what took their clicks from the table's selection. A table
    /// cell may carry neither a drag source nor a tap gesture; the row owns both.
    /// The Claims table's Source cell had the same fault and the same fix.
    @Test("no library-table cell carries a drag source or a tap gesture")
    func noCellTakesTheRowsClick() throws {
        let root = try AppSource.root()
        let paths = [
            "Views/Library/ViewModes/Table/LibraryView+TableColumns.swift",
            "Views/Library/ViewModes/Table/ClaimsTableView.swift"
        ]
        for path in paths {
            let source = try String(contentsOf: root.appendingPathComponent(path), encoding: .utf8)
            for forbidden in [".draggable(", ".onDrag(", ".onTapGesture", "TapGesture(", ".gesture("] {
                #expect(!source.contains(forbidden), "\(path) has \(forbidden)")
            }
        }
    }
}
