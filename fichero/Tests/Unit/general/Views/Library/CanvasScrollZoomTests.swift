@testable import Fichero
import Foundation
import Testing

/// ⌘-scroll zoom (#4601, `library.canvas.command-scroll-zooms-evenly`): a Magic Mouse flick never snaps the board to
/// its limit, zooming in and out go at the same speed, and the momentum glide does not zoom.
struct CanvasScrollZoomTests {
    @Test("a flick's huge delta is capped and never makes the scale zero or negative")
    func aFlickNeverSnaps() {
        for delta in [-5000.0, -250, -201, 0, 201, 5000] {
            #expect(CanvasScrollZoom.factor(delta: delta) > 0)
        }
        #expect(CanvasScrollZoom.factor(delta: -250) == CanvasScrollZoom.factor(delta: -CanvasScrollZoom.deltaCap))
        #expect(CanvasScrollZoom.factor(delta: 0) == 1)
    }

    @Test("in and out are the same speed: one step each way comes back to where it was")
    func inAndOutAreEven() {
        let there = CanvasScrollZoom.factor(delta: 25), back = CanvasScrollZoom.factor(delta: -25)
        #expect(abs(there * back - 1) < 1e-12)
        #expect(there > 1 && back < 1)
    }

    @Test("the glide after the fingers lift does not zoom")
    func momentumDoesNotZoom() {
        #expect(CanvasScrollZoom.zooms(isMomentum: false))
        #expect(!CanvasScrollZoom.zooms(isMomentum: true))
    }
}
