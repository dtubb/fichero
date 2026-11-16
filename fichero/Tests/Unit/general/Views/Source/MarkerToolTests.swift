@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.marker`. A Marker stroke that ends within
/// 12 points of where it began is a closed outline of the kind last drawn; any other is a baseline, a line whose outline
/// the engine draws from the ink. Either is ONE `segment.create` with `smoothing`, so the engine simplifies it on the
/// way in. M held is the Marker for one stroke; a tap of M chooses it. What breaks without these: a freehand region
/// stored a point per pixel, an open stroke made into a closed region, or a Marker that cannot be chosen by key.
@MainActor
@Suite(.tags(.paleography))
struct MarkerToolTests {
    private let page = CGSize(width: 1000, height: 1000)
    private let whole = CGRect(x: 0, y: 0, width: 1, height: 1)

    private func json(_ call: SegmentEdit.Call) throws -> [String: Any] {
        let data = try JSONEncoder().encode(call.params)
        return try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    @Test("a stroke that ends within 12 points of its start closes; one that ends further does not")
    func closes() {
        let loop: [[Double]] = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.105, 0.105]]
        #expect(MarkerStroke.isClosed(loop, size: page, visible: whole))
        let open: [[Double]] = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.12, 0.1]]
        #expect(!MarkerStroke.isClosed(open, size: page, visible: whole), "20 points away is open")
        // Zoomed in four times, the same 20 points is a smaller step on the page: still judged on screen.
        #expect(MarkerStroke.isClosed([[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.102, 0.1]], size: page,
                                      visible: CGRect(x: 0, y: 0, width: 0.25, height: 0.25)))
    }

    @Test("a closed stroke is one segment.create of the kind last drawn, outlined by the stroke, with smoothing")
    func closedStroke() throws {
        let loop: [[Double]] = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]
        let params = try json(MarkerStroke.create(
            loop, closed: true, closedKind: "region", on: StrokeTarget(documentId: "page-1", passId: "p", parentSegmentId: "r")
        ).get())
        #expect(params["kind"] as? String == "region")
        #expect(params["smoothing"] as? Double == MarkerStroke.smoothing)
        #expect(params["outline_from_baseline"] == nil)
        #expect(params["parent_segment_id"] == nil)
        let anchor = try #require(params["anchor"] as? [String: Any])
        #expect(anchor["polygon"] as? [[Double]] == loop)
    }

    @Test("an open stroke is a line on it as a baseline, in its region, its outline asked of the engine")
    func openStroke() throws {
        let stroke: [[Double]] = [[0.1, 0.3], [0.5, 0.31], [0.9, 0.3]]
        let params = try json(MarkerStroke.create(
            stroke, closed: false, closedKind: "region", on: StrokeTarget(documentId: "page-1", passId: "p", parentSegmentId: "r")
        ).get())
        #expect(params["kind"] as? String == "line")
        #expect(params["baseline"] as? [[Double]] == stroke)
        #expect(params["outline_from_baseline"] as? Bool == true)
        #expect(params["parent_segment_id"] as? String == "r")
        #expect(MarkerStroke.create([[0.1, 0.1]], closed: false, closedKind: "region",
                                    on: StrokeTarget(documentId: "d", passId: "p")) == .failure(.tooFew))
    }

    @Test("a tap of M chooses the Marker and puts the Knife down; M held for a stroke puts it back")
    func theKey() {
        let window = WindowState(libraryId: UUID())
        window.knifeArmed = true
        window.pressMarkerKey()
        window.letGoOfMarkerKey()
        #expect(window.markerArmed)
        #expect(!window.knifeArmed, "one tool at a time")
        window.markerArmed = false
        window.pressMarkerKey()
        window.markerStrokedWhileHeld = true
        window.letGoOfMarkerKey()
        #expect(!window.markerArmed)
        window.markerArmed = true
        window.activeMarkupTool = .drawRegion
        #expect(!window.markerArmed, "another tool puts the Marker down")
    }
}
