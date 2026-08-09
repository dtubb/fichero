@testable import Fichero
import Foundation
import Testing

// #34 (Daniel, 2026-08-09): ⌘-click add-to-selection was intermittent in
// icon view and "sometimes it deselects" — a click ON a tile that moved 4pt
// became a degenerate marquee sweep re-toggling the tile the tap had just
// toggled. The rubber band may only BEGIN in the gutter.
@Suite("LibraryMarquee.startsInGutter — sweeps begin on empty space only")
struct LibraryMarqueeGutterTests {
    private let frames: [String: CGRect] = [
        "a": CGRect(x: 0, y: 0, width: 100, height: 100),
        "b": CGRect(x: 120, y: 0, width: 100, height: 100)
    ]

    @Test("a point on a tile is not the gutter")
    func onTile() {
        #expect(!LibraryMarquee.startsInGutter(CGPoint(x: 50, y: 50), frames: frames))
        #expect(!LibraryMarquee.startsInGutter(CGPoint(x: 120, y: 0), frames: frames))
    }

    @Test("the gap between tiles and space below them is the gutter")
    func inGutter() {
        #expect(LibraryMarquee.startsInGutter(CGPoint(x: 110, y: 50), frames: frames))
        #expect(LibraryMarquee.startsInGutter(CGPoint(x: 50, y: 300), frames: frames))
        #expect(LibraryMarquee.startsInGutter(.zero, frames: [:]))
    }
}
