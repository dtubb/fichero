@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.draw-a-line`, `segment-editor.draw-kind-picker`,
/// `segment-editor.add-line-and-add-word`, `segment-editor.change-kind` (#7083). The polygon and rectangle tools make what the
/// chosen kind says, a line goes into the region that holds it, and the person can say so. What breaks without these: every
/// drawn shape a region, with no way to add a line.
@MainActor
@Suite(.tags(.paleography))
struct SegmentDrawLevelTests {
    private func segment(_ id: String, kind: String, rect: [Double], parent: String? = nil, version: Int? = 1) -> Segment {
        let anchor = SourceAnchorValue(
            generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1", rect: rect)
        )
        var made = Segment(
            id: id, provisional: false, documentId: "page-1", passId: "pass-1",
            kind: kind, kindRaw: nil, version: version, provenanceKind: .externalImport, anchor: anchor,
            baseline: nil, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
        made.parentSegmentId = parent
        return made
    }

    private let square = [[0.2, 0.2], [0.4, 0.2], [0.4, 0.3], [0.2, 0.3]]

    private func body(_ call: SegmentEdit.Call) throws -> [String: Any] {
        try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(call.params)) as? [String: Any])
    }

    @Test("a polygon made at a level is that kind, with its outline and the parent given")
    func polygonAtALevel() throws {
        let line = try SegmentShapes.create(
            .polygon, level: .line, points: square, documentId: "page-1", passId: "pass-1", onPass: nil, parentSegmentId: "r1"
        ).get()
        let sent = try body(line)
        #expect(sent["kind"] as? String == "line")
        #expect(sent["parent_segment_id"] as? String == "r1")
        #expect((sent["anchor"] as? [String: Any])?["polygon"] != nil)
        let word = try SegmentShapes.create(
            .polygon, level: .word, points: square, documentId: "page-1", passId: "pass-1", onPass: nil, parentSegmentId: "l1"
        ).get()
        #expect(try body(word)["kind"] as? String == "word")
    }

    @Test("with no level a polygon is still a region with no parent, as it always was")
    func defaultIsRegion() throws {
        let sent = try body(SegmentShapes.create(
            .polygon, points: square, documentId: "page-1", passId: "pass-1", onPass: nil, parentSegmentId: "r1"
        ).get())
        #expect(sent["kind"] as? String == "region")
        #expect(sent["parent_segment_id"] == nil)
    }

    @Test("the level follows the selection until one is chosen: a region selected draws a line, a line a word")
    func levelFollowsSelection() {
        let region = segment("r", kind: "region", rect: [0, 0, 1, 1])
        let line = segment("l", kind: "line", rect: [0, 0, 1, 0.1])
        #expect(SegmentShapes.level(chosen: nil, selected: []) == .region)
        #expect(SegmentShapes.level(chosen: nil, selected: [region]) == .line)
        #expect(SegmentShapes.level(chosen: nil, selected: [line]) == .word)
        #expect(SegmentShapes.level(chosen: nil, selected: [region, line]) == .region)
        #expect(SegmentShapes.level(chosen: .region, selected: [region]) == .region)
        #expect(SegmentShapes.level(chosen: .word, selected: []) == .word)
    }

    @Test("Add Line is offered on one region, Add Word on one line, neither on anything else")
    func addVerbs() {
        let region = segment("r", kind: "region", rect: [0, 0, 1, 1])
        let line = segment("l", kind: "line", rect: [0, 0, 1, 0.1])
        #expect(SegmentShapes.addLevel(for: [region]) == .line)
        #expect(SegmentShapes.addLevel(for: [line]) == .word)
        #expect(SegmentShapes.addLevel(for: [region, line]) == nil)
        #expect(SegmentShapes.addLevel(for: []) == nil)
        #expect(SegmentShapes.addLevel(for: [segment("w", kind: "word", rect: [0, 0, 0.1, 0.1])]) == nil)
    }

    @Test("a line goes into the region that holds it, a word into the line, and outside both there is no parent")
    func parents() {
        let region = segment("r", kind: "region", rect: [0.1, 0.1, 0.6, 0.6])
        let line = segment("l", kind: "line", rect: [0.15, 0.2, 0.5, 0.1], parent: "r")
        let page = [region, line]
        #expect(SegmentShapes.containingParent(for: square, level: .line, among: page)?.id == "r")
        let inLine = [[0.2, 0.22], [0.3, 0.22], [0.3, 0.28], [0.2, 0.28]]
        #expect(SegmentShapes.containingParent(for: inLine, level: .word, among: page)?.id == "l")
        #expect(SegmentShapes.containingParent(for: [[0.8, 0.8], [0.9, 0.8], [0.9, 0.9], [0.8, 0.9]], level: .line, among: page) == nil)
        #expect(SegmentShapes.containingParent(for: square, level: .region, among: page) == nil)
    }

    @Test("a line drawn outside every region says so")
    func noRegionNotice() {
        #expect(SegmentShapes.noRegionNotice == "This line is in no region")
    }

    @Test("Change Kind turns a region into a line and a line into a region, and offers nothing for a word")
    func changeKind() {
        #expect(SegmentShapes.changedKind(of: segment("r", kind: "region", rect: [0, 0, 1, 1])) == "line")
        #expect(SegmentShapes.changedKind(of: segment("l", kind: "line", rect: [0, 0, 1, 1])) == "region")
        #expect(SegmentShapes.changedKind(of: segment("w", kind: "word", rect: [0, 0, 1, 1])) == nil)
    }

    @Test("Change Kind is offered for regions and lines only: not for a word, a selection holding one, or none")
    func changeKindOffered() {
        let region = segment("r", kind: "region", rect: [0, 0, 1, 1])
        let line = segment("l", kind: "line", rect: [0, 0, 1, 0.1])
        let word = segment("w", kind: "word", rect: [0, 0, 0.1, 0.1])
        #expect(SegmentShapes.offersChangeKind([region]))
        #expect(SegmentShapes.offersChangeKind([region, line]))
        #expect(!SegmentShapes.offersChangeKind([word]))
        #expect(!SegmentShapes.offersChangeKind([line, word]))
        #expect(!SegmentShapes.offersChangeKind([]))
        #expect(!SegmentMenuTarget(
            isEditing: true, selectionCount: 1, toggleEditing: {}, canSelectAll: true, selectAll: {}, delete: {}, join: {},
            selectionHasBaselines: false, redraw: {}, apply: { _ in }
        ).canChangeKind)
    }
}
