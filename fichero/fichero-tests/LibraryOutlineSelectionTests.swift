@testable import Fichero
import Foundation
import Testing

// #4198 — Finder-style selection across expanded table rows.
// ⌘A / select-all spans the VISIBLE outline rows (children count only while
// their parent is expanded), and delete partitions the selection: documents
// are acted on, child rows are named in a plain skip message — never a
// silent no-op.

@Suite("Outline visible-row flattening (#4198)")
struct LibraryOutlineVisibleIdsTests {

    private func doc(_ id: String) -> Document {
        Document(id: id, name: id)
    }

    private func page(_ id: String, parent: String) -> Document {
        Document(id: id, parentId: parent, docType: .page, name: id, sequence: 1)
    }

    private func nodes() -> [LibraryOutlineNode] {
        let parent = doc("d1")
        let entityGroup = LibraryOutlineNode.childGroup(
            .entities,
            document: parent,
            count: 1,
            // Any node kind works for the flatten test; a page item keeps
            // the fixture free of generated KG types.
            children: [LibraryOutlineNode.pageItem(page("p2", parent: "d1"), parent: parent)]
        )
        let children = [
            LibraryOutlineNode.pageItem(page("p1", parent: "d1"), parent: parent),
            entityGroup
        ]
        return [
            LibraryOutlineNode.document(parent, children: children),
            LibraryOutlineNode.document(doc("d2"), children: nil)
        ]
    }

    @Test func collapsedOutlineYieldsOnlyTopLevelRows() {
        let ids = LibraryOutlineNode.visibleIds(of: nodes(), expanded: [])
        #expect(ids == ["d1", "d2"])
    }

    @Test func expandedDocumentIncludesItsDirectChildRows() {
        let ids = LibraryOutlineNode.visibleIds(of: nodes(), expanded: ["d1"])
        #expect(ids.contains("d1:page:p1"))
        #expect(ids.contains("d1:entities"))
        // The entity GROUP is collapsed — its nested rows stay invisible.
        #expect(ids.count == 4)
    }

    @Test func expandedGroupIncludesNestedRows() {
        let ids = LibraryOutlineNode.visibleIds(of: nodes(), expanded: ["d1", "d1:entities"])
        #expect(ids.count == 5)
    }

    @Test func expandedIdWithNilChildrenIsSafe() {
        // "d2" is expandable (document rows always are) but has no loaded
        // children — flattening must not crash or invent rows.
        let ids = LibraryOutlineNode.visibleIds(of: nodes(), expanded: ["d2"])
        #expect(ids == ["d1", "d2"])
    }
}

@Suite("Child-row classification and delete skip message (#4198)")
struct LibraryOutlineDeleteSkipTests {

    @Test func childRowTypeParsesItemAndGroupIds() {
        #expect(LibraryOutlineNode.childRowType(forNodeId: "d1:page:p9") == .pages)
        #expect(LibraryOutlineNode.childRowType(forNodeId: "d1:pages") == .pages)
        #expect(LibraryOutlineNode.childRowType(forNodeId: "d1:artifact:a1") == .artifacts)
        #expect(LibraryOutlineNode.childRowType(forNodeId: "d1:entity:e1") == .entities)
        #expect(LibraryOutlineNode.childRowType(forNodeId: "d1:claim:c1") == .claims)
        #expect(LibraryOutlineNode.childRowType(forNodeId: "d1:notes") == .notes)
    }

    @Test func plainDocumentIdsAreNotChildRows() {
        #expect(LibraryOutlineNode.childRowType(forNodeId: "plain-doc-id") == nil)
        // Document ids may themselves contain colons (default-workflow
        // subfolders) — an unknown marker must read as "not a child row".
        #expect(LibraryOutlineNode.childRowType(forNodeId: "system-default-workflows:books") == nil)
    }

    @Test func skipNoteIsNilForEmptyOrDocumentOnlySelections() {
        #expect(LibraryView.skippedChildRowNote(for: []) == nil)
    }

    @Test func skipNoteCountsEachKind() throws {
        let note = try #require(LibraryView.skippedChildRowNote(for: [
            "d1:page:p1", "d1:page:p2", "d1:entity:e1"
        ]))
        #expect(note.contains("2 pages"))
        #expect(note.contains("1 entity"))
        #expect(note.contains("Skipped"))
        // Says what to do instead — not just what went wrong.
        #expect(note.contains("document row"))
    }

    @Test func unknownColonIdsCountAsGenericItems() throws {
        let note = try #require(LibraryView.skippedChildRowNote(for: [
            "system-default-workflows:books"
        ]))
        #expect(note.contains("1 item"))
    }
}
