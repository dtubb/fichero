import CoreGraphics
@testable import Fichero
import Testing

/// #5142: a scroll of a dense page redraws only the strip it exposes. What breaks without it: every
/// tick paints every box again -- the 4,525-box lag this overlay exists to remove.
struct DocumentOverlayTests {
    private let page = CGSize(width: 1000, height: 1000)

    private func overlay() -> DocumentOverlay {
        DocumentOverlay(boxes: [
            .init(bbox: [0.1, 0.1, 0.1, 0.1], confidence: 1),     // near the TOP of the page
            .init(bbox: [0.1, 0.8, 0.1, 0.1], confidence: 0.3),   // near the BOTTOM
            .init(bbox: [0, 0, 0, 0], confidence: nil)           // a placeholder: never drawn
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

    /// #5142: saved marks move with the page too. Geometry kinds draw inside the scroll view; the
    /// glyph and tappable kinds stay in SwiftUI. What breaks without it: a highlight drawn twice (both
    /// layers) or not at all (neither), or a note that can no longer be tapped.
    @Test("the geometry kinds draw here, the glyph and tappable kinds stay in SwiftUI")
    func markKinds() {
        #expect(DocumentOverlay.Mark.shape(for: .highlight) == .wash)
        #expect(DocumentOverlay.Mark.shape(for: .underline) == .underline)
        #expect(DocumentOverlay.Mark.shape(for: .strikethrough) == .strike)
        #expect(DocumentOverlay.Mark.shape(for: .line) == .line)
        #expect(DocumentOverlay.Mark.shape(for: .unknown) == .box)
        for kind in [AnnotationKind.rating, .note, .bookmark] {
            #expect(DocumentOverlay.Mark.shape(for: kind) == nil, "\(kind) must stay in SwiftUI")
        }
    }

    @Test("a new mark or a newly selected mark redraws")
    func marksRedraw() {
        var marked = DocumentOverlay()
        marked.marks = [.init(shape: .wash, bbox: [0.1, 0.1, 0.2, 0.05], color: nil)]
        #expect(marked != DocumentOverlay())
        var chosen = DocumentOverlay()
        chosen.selectedMark = [0.1, 0.1, 0.2, 0.05]
        #expect(chosen != DocumentOverlay())
    }
    /// `segment-editor.order-overlay` (docs/contributor_manual/specs/ui/segment-editor.md): with the order shown, an
    /// arrow runs from each numbered line's start to the next number's, in number order, never across a gap.
    @Test("the order arrows join each numbered line to the next, in number order")
    func orderArrows() {
        func line(_ number: Int?, _ top: Double) -> DocumentOverlay.Box {
            var box = DocumentOverlay.Box(bbox: [0.1, top, 0.5, 0.04], confidence: nil)
            box.orderNumber = number
            return box
        }
        let shown = DocumentOverlay(boxes: [line(2, 0.3), line(nil, 0.0), line(1, 0.2), line(4, 0.6), line(3, 0.4)], selected: [])
        let arrows = shown.orderArrows()
        #expect(arrows.map(\.from) == [[0.1, 0.2], [0.1, 0.3], [0.1, 0.4]])
        #expect(arrows.map(\.to) == [[0.1, 0.3], [0.1, 0.4], [0.1, 0.6]])
        let gap = DocumentOverlay(boxes: [line(1, 0.2), line(3, 0.4)], selected: [])
        #expect(gap.orderArrows().isEmpty, "no arrow across a missing number")
    }
}
