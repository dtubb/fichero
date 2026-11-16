@testable import Fichero
import Foundation
import Testing
import UniformTypeIdentifiers

// Spec: source.editor.order-list-edits-like-finder (#6476), source/segment-editor-crud.md.
//
// A click anywhere on an Order list row selects it, its words included. The words did not select
// because the row's content carried `.draggable`, which takes the mouse-down before the List sees
// it (the Library table's same fault, #6538). The ROW now drags, through `View.itemProvider` with
// `SegmentDrag.itemProvider()`. The List drags every selected row and asks each for its item, so a
// row carries only itself (`SegmentDrag.forRow`): four rows to the Desktop are four clippings, one
// line each, and a drop on a region gathers their ids again.

@Suite("Order list: the row drags itself (#6476)")
struct SegmentDragRowTests {

    private let order = ["l1", "l2", "l3", "l4"]
    private let words = ["l1": "uno", "l2": "dos", "l3": "tres", "l4": "cuatro"]

    @Test("a row carries itself alone, its words as the text")
    func rowCarriesItself() {
        #expect(SegmentDrag.forRow("l3") { words[$0] } == SegmentDrag(ids: ["l3"], text: "tres"))
    }

    @Test("four rows dragged are four items of one line each, gathered again on a drop")
    func fourRowsAreFourItems() {
        let items = ["l1", "l2", "l3", "l4"].map { id in SegmentDrag.forRow(id) { words[$0] } }
        #expect(items.map(\.text) == ["uno", "dos", "tres", "cuatro"])
        #expect(items.flatMap(\.ids) == order)
    }

    @Test("the row's item provider carries the app's own line drag and the words as text")
    func itemProviderCarriesBothRepresentations() {
        let provider = SegmentDrag(ids: ["l1"], text: "uno").itemProvider()
        let types = provider.registeredTypeIdentifiers
        #expect(types.contains(UTType.segmentDrag.identifier))
        #expect(types.contains { UTType($0)?.conforms(to: .plainText) == true })
    }
}
