@testable import Fichero
import Foundation
import Testing

// #95 (2026-08-09): a multi-selection previews as a Finder-style fanned
// stack. These pin the file-scope resolver the two preview call sites gate on.
@Suite("previewStackDocuments — the multi-selection preview gate")
struct MultiSelectionPreviewStackTests {
    private let docs = [
        Document(id: "a", name: "A"),
        Document(id: "b", name: "B"),
        Document(id: "c", name: "C")
    ]

    @Test("multiple selected documents resolve in DOCUMENT order, not set order")
    func documentOrder() {
        let stack = previewStackDocuments(selection: ["c", "a"], in: docs)
        #expect(stack.map(\.id) == ["a", "c"])
    }

    @Test("a single or empty selection never stacks")
    func singleAndEmptyGate() {
        #expect(previewStackDocuments(selection: ["a"], in: docs).isEmpty)
        #expect(previewStackDocuments(selection: [], in: docs).isEmpty)
    }

    @Test("ids that resolve to fewer than two live documents never stack")
    func unresolvedIdsGate() {
        // Two selected ids but only one resolves — previewing a 'stack' of
        // one would misstate the selection; the single-preview path owns it.
        #expect(previewStackDocuments(selection: ["a", "ghost"], in: docs).map(\.id) == [])
    }

    @Test("the front card is the document-order primary and back cards fan")
    func fanGeometry() {
        #expect(stackRotationDegrees(forCardAt: 0) == 0)
        #expect(stackRotationDegrees(forCardAt: 1) != 0)
        #expect(stackRotationDegrees(forCardAt: 2) != 0)
    }
}
