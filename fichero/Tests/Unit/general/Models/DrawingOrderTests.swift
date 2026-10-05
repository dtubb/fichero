@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `SegmentDisplay.drawingOrder`: the ONE order the Preview tries a page's passes in (#5467). The app ranks
/// nothing itself: the inspector's focused artifact first (ruled 2026-08-27), then the pass the engine marks
/// `drawn`, then the rest by the engine's `rank`. Before #5467 the app kept its own copy of the engine's
/// ladder (curated, then newest, then legacy by type), and the two could name different passes: the canvas
/// drew one pass while the list and the text read another. Behaviours: `source.app.overlays-draw-from-the-seam`,
/// `ui.preview.draws-a-pass-with-shapes`.
struct DrawingOrderTests {

    private func pass(
        _ id: String, drawn: Bool = false, rank: Int?, artifactId: String? = nil, ageInHours: Double = 0
    ) -> SegmentPassValue {
        var pass = SegmentPassValue(
            id: id, provisional: false, documentId: "page-1", name: id, provenanceKind: .workflow,
            createdAt: Date(timeIntervalSince1970: 1_000_000 - ageInHours * 3600),
            sourceArtifactId: artifactId, artifactType: nil
        )
        pass.drawn = drawn
        pass.rank = rank
        pass.working = rank == 0
        return pass
    }

    /// One boxed segment of `passId`, so the pass has a shape to draw.
    private func boxed(_ passId: String) -> Segment {
        var anchor = SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1"))
        anchor.rect = [0.1, 0.1, 0.5, 0.05]
        return Segment(
            id: "\(passId)-0", provisional: false, documentId: "page-1", passId: passId, kind: "line",
            kindRaw: nil, provenanceKind: .workflow, anchor: anchor, baseline: nil, text: "a line",
            confidence: nil, sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
    }

    /// WHY: the engine says which pass the image draws; a newer or a person's pass the engine ranked lower
    /// must not jump it by an app rule (the duplicate ladder #5467 deleted).
    @Test("the engine's drawn pass is first, whatever is newer beside it")
    func theDrawnPassIsFirst() {
        let newer = pass("newer", rank: 1, ageInHours: 0)
        let drawn = pass("working", drawn: true, rank: 0, ageInHours: 48)
        #expect(SegmentDisplay.drawingOrder([newer, drawn], segments: []).map(\.id) == ["working", "newer"])
    }

    /// WHY: when the working pass has no shapes the engine marks the next pass with shapes `drawn`
    /// (ruled 2026-10-04); the working pass follows it, by its rank, rather than being dropped.
    @Test("a shapeless working pass comes after the drawn pass, by its rank")
    func aShapelessWorkingPassFollowsTheDrawnPass() {
        let working = pass("tei-import", rank: 0)
        let drawn = pass("kraken", drawn: true, rank: 1)
        let other = pass("vision", rank: 2)
        #expect(SegmentDisplay.drawingOrder([other, working, drawn], segments: []).map(\.id)
                == ["kraken", "tei-import", "vision"])
    }

    /// WHY: a page with no shapes at all has no drawn pass; its working pass (rank 0) must still come
    /// first, so a text-only page selects its own lines.
    @Test("with no drawn pass, the engine's rank orders, the working pass first")
    func withNoDrawnPassTheRankOrders() {
        let ranked = SegmentDisplay.drawingOrder(
            [pass("c", rank: 2), pass("unranked", rank: nil), pass("a", rank: 0), pass("b", rank: 1)], segments: []
        )
        #expect(ranked.map(\.id) == ["a", "b", "c", "unranked"])
    }

    /// WHY (#5122): a georeferencing pass holds control points and a mask, not the page's text; drawn as the
    /// page's boxes it blanked a page.
    @Test("a georeferencing pass is never in the order")
    func aGeoreferenceIsLeftOut() {
        var georef = pass("georef", drawn: true, rank: nil)
        georef.transformation = "thin-plate-spline"
        #expect(SegmentDisplay.drawingOrder([georef, pass("text", rank: 0)], segments: []).map(\.id) == ["text"])
    }

    /// WHY (ruled 2026-08-27, "when I click on different regions in artifacts, should bounding boxes
    /// update?" -- yes): the Inspector's focused artifact goes first when this page has a pass from it with
    /// a shape, ahead of the engine's drawn pass.
    @Test("the focused artifact's pass goes first when it has a shape")
    func theFocusedArtifactGoesFirst() {
        let drawn = pass("working", drawn: true, rank: 0, artifactId: "art-working")
        let clicked = pass("clicked", rank: 1, artifactId: "art-clicked")
        let order = SegmentDisplay.drawingOrder(
            [drawn, clicked], segments: [boxed("working"), boxed("clicked")], focusedArtifactId: "art-clicked"
        )
        #expect(order.map(\.id) == ["clicked", "working"])
    }

    /// WHY: a REORDER, never a filter. A focused artifact with nothing to draw -- no shapes, or another
    /// page's artifact -- falls through to the engine's order instead of blanking the page.
    @Test("a focused artifact with no shapes, or not on this page, changes nothing")
    func anUnusableFocusChangesNothing() {
        let drawn = pass("working", drawn: true, rank: 0, artifactId: "art-working")
        let clicked = pass("clicked", rank: 1, artifactId: "art-clicked")
        let shapeless = SegmentDisplay.drawingOrder(
            [drawn, clicked], segments: [boxed("working")], focusedArtifactId: "art-clicked"
        )
        #expect(shapeless.map(\.id) == ["working", "clicked"])
        let elsewhere = SegmentDisplay.drawingOrder(
            [drawn, clicked], segments: [boxed("working"), boxed("clicked")], focusedArtifactId: "art-another-page"
        )
        #expect(elsewhere.map(\.id) == ["working", "clicked"])
    }
}
