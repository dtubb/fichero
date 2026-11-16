@testable import Fichero
import FicheroAPIClient
import Testing

/// Return in the Order list (Step 1.25). What breaks without these: Return renaming nothing, or a region or a
/// multi-selection starting an edit that has nowhere to go, or an unchanged commit recording a new reading.
struct OrderRenameTests {
    private func segment(_ id: String, kind: String, text: String? = nil) -> Segment {
        Segment(
            id: id, provisional: false, documentId: "p1", passId: "p", kind: kind, kindRaw: nil,
            parentSegmentId: nil, provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1")),
            baseline: nil, text: text, confidence: nil, sourceArtifactId: nil, boxIndex: nil, pageIndex: nil, metadata: nil
        )
    }

    @Test("Return begins an edit on one line, with its words; on none, several, or a region it does not")
    func begins() {
        let line = segment("l1", kind: "line", text: "Dos Mesas")
        #expect(OrderRename.begins(on: [line]) == "Dos Mesas")
        #expect(OrderRename.begins(on: [segment("l2", kind: "line")]) == "")
        #expect(OrderRename.begins(on: []) == nil)
        #expect(OrderRename.begins(on: [line, segment("l3", kind: "line")]) == nil)
        #expect(OrderRename.begins(on: [segment("r1", kind: "region")]) == nil)
    }

    @Test("the commit sends changed words trimmed, and nothing for the same or empty words")
    func commit() {
        let line = segment("l1", kind: "line", text: "Dos Mesas")
        #expect(OrderRename.commit("  Dos Mesas la Una ", on: line) == "Dos Mesas la Una")
        #expect(OrderRename.commit("Dos Mesas", on: line) == nil)
        #expect(OrderRename.commit("   ", on: line) == nil)
    }
}
