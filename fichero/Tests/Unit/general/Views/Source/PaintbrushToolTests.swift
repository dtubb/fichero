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
