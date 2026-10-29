import Foundation
@testable import Fichero
import Testing

/// The page-corner handles in Crop (`prep.square.corner-handles-correct-it`): the maths behind the four dashed handles.
struct ImageEditDirectToolsTests {
    private let region: [String: Any] = ["quad": [[0.1, 0.1], [0.9, 0.12], [0.88, 0.9], [0.12, 0.88]], "method": "contour"]

    @Test("a page_region's quad becomes four corners, top-left clockwise")
    func readsPageRegion() throws {
        let corners = try #require(PageCorners(pageRegion: region))
        #expect(corners.points.count == 4)
        #expect(corners.points[1] == CGPoint(x: 0.9, y: 0.12))
    }

    @Test("no quad, or not four corners, shows no handles")
    func noHandlesWithoutAQuad() {
        #expect(PageCorners(pageRegion: nil) == nil)
        #expect(PageCorners(pageRegion: ["quad": [[0, 0], [1, 0], [1, 1]]]) == nil)
        #expect(PageCorners(pageRegion: ["method": "vision"]) == nil)
    }

    @Test("dragging one corner moves only it, and stays inside the image")
    func dragMovesOneCornerClamped() throws {
        let corners = try #require(PageCorners(pageRegion: region))
        let moved = corners.moving(2, to: CGPoint(x: 1.4, y: -0.2))
        #expect(moved.points[2] == CGPoint(x: 1, y: 0))
        #expect(moved.points[0] == corners.points[0] && moved.points[1] == corners.points[1] && moved.points[3] == corners.points[3])
    }

    @Test("a press picks the nearest corner within reach, else none")
    func pressPicksNearestCorner() throws {
        let corners = try #require(PageCorners(pageRegion: region))
        #expect(corners.corner(near: CGPoint(x: 0.11, y: 0.11), radius: 0.04) == 0)
        #expect(corners.corner(near: CGPoint(x: 0.5, y: 0.5), radius: 0.04) == nil)
    }

    @Test("Return sends the corrected corners as [x, y] pairs")
    func quadIsTheWireForm() throws {
        let corners = try #require(PageCorners(pageRegion: region)).moving(0, to: CGPoint(x: 0.2, y: 0.3))
        #expect(corners.quad == [[0.2, 0.3], [0.9, 0.12], [0.88, 0.9], [0.12, 0.88]])
    }
}
