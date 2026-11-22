@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.paintbrush`. A stroke painted along a
/// line of ink is ONE `segment.create` of a line, every point carrying the brush's width in image pixels, so the engine
/// makes the outline and the baseline; the width on screen becomes image pixels by the zoom. What breaks without
/// these: a stroke sent without its width, or a width measured in screen points that changes with the zoom.
@MainActor
@Suite(.tags(.paleography))
struct PaintbrushToolTests {
    @Test("a screen width becomes image pixels by the zoom")
    func pixels() {
        // A 1000-point view showing half of a 4000-pixel image: a point is two pixels.
        #expect(PaintbrushStroke.pixels(20, viewWidth: 1000, visibleWidth: 0.5, imageWidth: 4000) == 40)
        #expect(PaintbrushStroke.pixels(20, viewWidth: 1000, visibleWidth: 1, imageWidth: 4000) == 80)
    }

    @Test("the stroke is one segment.create of a line, each point with the brush's width, in its region")
    func oneCall() throws {
        let stroke: [[Double]] = [[0.1, 0.3], [0.5, 0.3], [0.9, 0.31]]
        let call = try PaintbrushStroke.create(
            stroke, widthPixels: 30, on: StrokeTarget(documentId: "page-1", passId: "p", parentSegmentId: "r")
        ).get()
        let data = try JSONEncoder().encode(call.params)
        let params = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(call.action == "segment.create")
        #expect(params["kind"] as? String == "line")
        #expect(params["brush_stroke"] as? [[Double]] == [[0.1, 0.3, 30], [0.5, 0.3, 30], [0.9, 0.31, 30]])
        #expect(params["parent_segment_id"] as? String == "r")
        #expect(PaintbrushStroke.create([[0.1, 0.3]], widthPixels: 30,
                                        on: StrokeTarget(documentId: "d", passId: "p")) == .failure(.tooFew))
    }

    @Test("[ and ] change the width within its bounds; another tool puts the Paintbrush down")
    func widthAndTool() {
        let window = WindowState(libraryId: UUID())
        for _ in 0..<30 { window.resizePaint(larger: true) }
        #expect(window.paintWidth == 120)
        for _ in 0..<30 { window.resizePaint(larger: false) }
        #expect(window.paintWidth == 4)
        window.activeMarkupTool = .select
        window.paintArmed = true
        window.activeMarkupTool = .drawRegion
        #expect(!window.paintArmed)
    }
}

/// What breaks without these: a Paintbrush stroke on a page that has a result artifact was dropped with only a log line
/// (the gate wanted an artifact-less pass), so nothing was recorded and the page said nothing (#6734).
@MainActor
@Suite(.tags(.paleography))
struct PaintbrushTargetTests {
    private func segment(_ id: String, provisional: Bool = false) -> Segment {
        Segment(
            id: id, provisional: provisional, documentId: "d", passId: "p", kind: "region", kindRaw: nil,
            provenanceKind: .workflow, anchor: SourceAnchorValue(generated: .init(documentId: "d")),
            baseline: nil, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: nil, pageIndex: nil, metadata: nil
        )
    }

    private func refusal(_ result: Result<StrokeTarget, StrokeRefusal>) -> StrokeRefusal? {
        if case .failure(let why) = result { return why }
        return nil
    }

    @Test("a shown pass takes the stroke whether or not it has an artifact; the region holding it is the parent")
    func resolves() throws {
        let region = segment("r")
        let target = try StrokeTarget.resolve(documentId: "d", passId: "p", onPass: [region], region: region).get()
        #expect(target.documentId == "d" && target.passId == "p" && target.parentSegmentId == "r")
        let call = try PaintbrushStroke.create([[0.1, 0.3], [0.5, 0.3]], widthPixels: 20, on: target).get()
        #expect(call.action == "segment.create")
    }

    @Test("no pass, a legacy pass or a provisional segment is refused with words for the page")
    func refuses() {
        #expect(refusal(StrokeTarget.resolve(documentId: "d", passId: nil, onPass: [], region: nil)) == .noPass)
        #expect(refusal(StrokeTarget.resolve(documentId: nil, passId: "p", onPass: [], region: nil)) == .noPass)
        #expect(refusal(StrokeTarget.resolve(documentId: "d", passId: "legacy:x", onPass: [], region: nil)) == .notSaved)
        let provisional = segment("s", provisional: true)
        #expect(refusal(StrokeTarget.resolve(documentId: "d", passId: "p", onPass: [provisional], region: nil)) == .notSaved)
        #expect(!StrokeRefusal.noPass.words.isEmpty)
    }

    @Test("a refused edit says what was not sent")
    func notSent() {
        #expect(SegmentEdit.notSentWords("Cut Lines", .tooFew).hasPrefix("Cut Lines: "))
    }
}
