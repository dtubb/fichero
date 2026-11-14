@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.reassign-by-drag`. Lines dragged in Select
/// and let go on another region become that region's lines; on no region, the page's; inside their own region the shapes
/// move; ⌘ held always moves. What breaks without these: a drag across a region boundary that only moves the box, leaving
/// the line read in the wrong region, or a nudge inside a region that reassigns it.
@MainActor
@Suite(.tags(.paleography))
struct ReassignDragTests {
    private func segment(_ id: String, _ kind: String, rect: [Double], parent: String? = nil) -> Segment {
        var row = Segment(
            id: id, provisional: false, documentId: "page-1", passId: "imported",
            kind: kind, kindRaw: nil, version: 1, provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1", rect: rect)),
            baseline: nil, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
        row.parentSegmentId = parent
        return row
    }

    private var page: [Segment] {
        [
            segment("left", "region", rect: [0.0, 0.0, 0.5, 1.0]),
            segment("right", "region", rect: [0.5, 0.0, 0.5, 0.8]),
            segment("stamp", "region", rect: [0.6, 0.1, 0.1, 0.1]),
            segment("line", "line", rect: [0.1, 0.1, 0.3, 0.05], parent: "left"),
            segment("loose", "line", rect: [0.1, 0.9, 0.3, 0.05])
        ]
    }

    private func line(_ id: String) -> Segment { page.first { $0.id == id }! }

    @Test("a line let go on another region is reassigned to it; the smaller region wins where two overlap")
    func ontoAnotherRegion() {
        #expect(SegmentMover.drop(of: [line("line")], at: [0.8, 0.5], among: page, commandHeld: false) == .reassign(into: "right"))
        #expect(SegmentMover.drop(of: [line("line")], at: [0.65, 0.15], among: page, commandHeld: false) == .reassign(into: "stamp"))
    }

    @Test("a line let go on no region is lifted out to the page; a regionless line let go on a region joins it")
    func ontoNoRegion() {
        #expect(SegmentMover.drop(of: [line("line")], at: [0.8, 0.9], among: page, commandHeld: false) == .reassign(into: nil))
        #expect(SegmentMover.drop(of: [line("loose")], at: [0.2, 0.5], among: page, commandHeld: false) == .reassign(into: "left"))
    }

    @Test("inside its own region, with ⌘ held, or with a region among the dragged, the shapes move")
    func movesInstead() {
        #expect(SegmentMover.drop(of: [line("line")], at: [0.2, 0.5], among: page, commandHeld: false) == .move)
        #expect(SegmentMover.drop(of: [line("line")], at: [0.8, 0.5], among: page, commandHeld: true) == .move)
        #expect(SegmentMover.drop(of: [line("line"), page[1]], at: [0.2, 0.5], among: page, commandHeld: false) == .move)
    }

    @Test("lines from two regions let go on one of them are all reassigned to it, as one call")
    func aSelectionFromTwoRegions() throws {
        var other = line("loose")
        other.parentSegmentId = "right"
        let dragged = [line("line"), other]
        #expect(SegmentMover.drop(of: dragged, at: [0.2, 0.5], among: page, commandHeld: false) == .reassign(into: "left"))
        let call = try SegmentEdit.reparent(dragged, into: "left").get()
        #expect(call.action == "segment.reparent")
    }
}
