@testable import Fichero
import CoreGraphics
import Testing

/// #5142: a scroll of a dense page redraws only the strip it exposes. What breaks without it: every
/// tick paints every box again -- the 4,525-box lag this overlay exists to remove.
struct DocumentOverlayTests {
    private let page = CGSize(width: 1000, height: 1000)

    private func overlay() -> DocumentOverlay {
        DocumentOverlay(boxes: [
            .init(bbox: [0.1, 0.1, 0.1, 0.1], confidence: 1),     // near the TOP of the page
            .init(bbox: [0.1, 0.8, 0.1, 0.1], confidence: 0.3),   // near the BOTTOM
            .init(bbox: [0, 0, 0, 0], confidence: nil),           // a placeholder: never drawn
        ], selected: [[0.1, 0.8, 0.1, 0.1]])
    }

    @Test("a redraw of the bottom strip paints only the boxes in it")
    func onlyTheExposedStrip() {
        // The bottom of the page is LOW y in the unflipped document space.
        let bottomStrip = CGRect(x: 0, y: 0, width: 1000, height: 250)
        let drawn = overlay().boxes(in: bottomStrip, imageRect: CGRect(origin: .zero, size: page))
        #expect(drawn.map(\.box.bbox) == [[0.1, 0.8, 0.1, 0.1]])
        #expect(overlay().selected(in: bottomStrip, imageRect: CGRect(origin: .zero, size: page)).count == 1)
        let topStrip = CGRect(x: 0, y: 750, width: 1000, height: 250)
        #expect(overlay().boxes(in: topStrip, imageRect: CGRect(origin: .zero, size: page)).map(\.box.bbox) == [[0.1, 0.1, 0.1, 0.1]])
        #expect(overlay().selected(in: topStrip, imageRect: CGRect(origin: .zero, size: page)).isEmpty)
    }

    @Test("a placeholder box is never painted, whatever is redrawn")
    func placeholdersNeverPaint() {
        let everything = CGRect(origin: .zero, size: page)
        #expect(overlay().boxes(in: everything, imageRect: CGRect(origin: .zero, size: page)).count == 2)
    }

    @Test("the same overlay is equal, so an unchanged page does not redraw")
    func equalityStopsRedraws() {
        #expect(overlay() == overlay())
        var moved = overlay()
        moved.selected = []
        #expect(moved != overlay())
    }

    /// The entry wash and the Reader-linked words ride the same view, so they move with the words
    /// they mark instead of lagging behind them like the rest of the SwiftUI overlay did.
    @Test("washes are painted only where a redraw asks, and a new wash redraws")
    func washesFollowTheDirtyRect() {
        let bottomStrip = CGRect(x: 0, y: 0, width: 1000, height: 250)
        let washes = [[0.1, 0.8, 0.2, 0.05], [0.1, 0.1, 0.2, 0.05]]   // one low, one high on the page
        #expect(DocumentOverlay.rects(washes, in: bottomStrip, imageRect: CGRect(origin: .zero, size: page)).count == 1)
        var lit = overlay()
        lit.linkedWashes = [[0.1, 0.8, 0.2, 0.05]]
        #expect(lit != overlay())
    }
}
