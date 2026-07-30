import CoreGraphics
@testable import Fichero
import Testing

/// #4279 — a preview must open at fit-to-view, not at a fixed too-small scale.
/// Raster content is capped at 100% (never upscaled past its pixels); vector
/// content (PDF) fits with no cap. These lock the arithmetic that both the
/// image viewer and the PDF viewer now share.
struct PreviewInitialZoomPolicyTests {

    /// CGFloat division isn't exact for every ratio; compare with a tolerance.
    private func isClose(_ lhs: CGFloat, _ rhs: CGFloat, tolerance: CGFloat = 0.0001) -> Bool {
        abs(lhs - rhs) < tolerance
    }

    // MARK: - Raster

    @Test("A raster image smaller than the pane opens at 100%, not blown up")
    func rasterSmallerThanPaneIsNotUpscaled() {
        let scale = PreviewInitialZoomPolicy.initialScale(
            contentSize: CGSize(width: 400, height: 300),
            paneSize: CGSize(width: 1000, height: 800),
            kind: .raster
        )
        // Fit alone would be 2.5×; the raster cap holds it at 1.0.
        #expect(isClose(scale, 1.0))
    }

    @Test("A raster image larger than the pane opens fitted, below 100%")
    func rasterLargerThanPaneFits() {
        let scale = PreviewInitialZoomPolicy.initialScale(
            contentSize: CGSize(width: 2000, height: 1000),
            paneSize: CGSize(width: 1000, height: 1000),
            kind: .raster
        )
        #expect(isClose(scale, 0.5))
        #expect(scale < 1.0)
    }

    @Test("A raster image exactly the size of the pane opens at 100%")
    func rasterExactFit() {
        let scale = PreviewInitialZoomPolicy.initialScale(
            contentSize: CGSize(width: 800, height: 600),
            paneSize: CGSize(width: 800, height: 600),
            kind: .raster
        )
        #expect(isClose(scale, 1.0))
    }

    // MARK: - Vector (PDF)

    @Test("A PDF page larger than the pane opens fitted")
    func vectorLargerThanPaneFits() {
        let scale = PreviewInitialZoomPolicy.initialScale(
            contentSize: CGSize(width: 612, height: 792),  // US Letter, points
            paneSize: CGSize(width: 306, height: 396),
            kind: .vector
        )
        #expect(isClose(scale, 0.5))
    }

    @Test("A PDF page smaller than the pane fills it — vector has no 100% cap")
    func vectorSmallerThanPaneIsUpscaled() {
        let scale = PreviewInitialZoomPolicy.initialScale(
            contentSize: CGSize(width: 306, height: 396),
            paneSize: CGSize(width: 612, height: 792),
            kind: .vector
        )
        #expect(isClose(scale, 2.0))
        #expect(scale > 1.0, "vector content must be allowed past 100%")
    }

    @Test("The same undersized item caps for raster but not for vector")
    func capAppliesOnlyToRaster() {
        let content = CGSize(width: 200, height: 200)
        let pane = CGSize(width: 800, height: 800)
        let raster = PreviewInitialZoomPolicy.initialScale(contentSize: content, paneSize: pane, kind: .raster)
        let vector = PreviewInitialZoomPolicy.initialScale(contentSize: content, paneSize: pane, kind: .vector)
        #expect(isClose(raster, 1.0))
        #expect(isClose(vector, 4.0))
    }

    // MARK: - Fit axis

    @Test("A portrait item in a landscape pane is constrained by height")
    func portraitInLandscapePaneFitsByHeight() {
        let scale = PreviewInitialZoomPolicy.initialScale(
            contentSize: CGSize(width: 500, height: 1000),
            paneSize: CGSize(width: 1000, height: 500),
            kind: .vector
        )
        // Width alone would allow 2.0×; height only allows 0.5×.
        #expect(isClose(scale, 0.5))
    }

    @Test("A landscape item in a portrait pane is constrained by width")
    func landscapeInPortraitPaneFitsByWidth() {
        let scale = PreviewInitialZoomPolicy.initialScale(
            contentSize: CGSize(width: 1000, height: 500),
            paneSize: CGSize(width: 500, height: 1000),
            kind: .vector
        )
        #expect(isClose(scale, 0.5))
    }

    // MARK: - Degenerate geometry

    @Test("An unmeasured pane yields no fit scale rather than infinity")
    func unmeasuredPaneHasNoFitScale() {
        #expect(PreviewInitialZoomPolicy.fitScale(
            contentSize: CGSize(width: 800, height: 600),
            paneSize: .zero
        ) == nil)
        #expect(PreviewInitialZoomPolicy.fitScale(
            contentSize: .zero,
            paneSize: CGSize(width: 800, height: 600)
        ) == nil)
    }

    @Test("Zero, negative and non-finite sizes fall back to 100%, never 0 or NaN")
    func degenerateSizesFallBackToNeutral() {
        let cases: [(CGSize, CGSize)] = [
            (CGSize(width: 800, height: 600), .zero),
            (.zero, CGSize(width: 800, height: 600)),
            (.zero, .zero),
            (CGSize(width: -800, height: 600), CGSize(width: 800, height: 600)),
            (CGSize(width: 800, height: 600), CGSize(width: 800, height: -600)),
            (CGSize(width: .nan, height: 600), CGSize(width: 800, height: 600)),
            (CGSize(width: 800, height: 600), CGSize(width: .infinity, height: 600))
        ]
        for (content, pane) in cases {
            for kind in [PreviewContentKind.raster, .vector] {
                let scale = PreviewInitialZoomPolicy.initialScale(
                    contentSize: content,
                    paneSize: pane,
                    kind: kind
                )
                #expect(isClose(scale, PreviewInitialZoomPolicy.neutralScale),
                        "\(content) in \(pane) as \(kind) must fall back to the neutral scale")
            }
        }
    }

    // MARK: - clamped(_:kind:) — the entry point the PDF viewer uses

    @Test("clamped caps a raster scale at 100% and leaves vector untouched")
    func clampedAppliesTheKindsCap() {
        #expect(isClose(PreviewInitialZoomPolicy.clamped(3.0, kind: .raster), 1.0))
        #expect(isClose(PreviewInitialZoomPolicy.clamped(0.4, kind: .raster), 0.4))
        #expect(isClose(PreviewInitialZoomPolicy.clamped(3.0, kind: .vector), 3.0))
        #expect(isClose(PreviewInitialZoomPolicy.clamped(0.4, kind: .vector), 0.4))
    }

    @Test("clamped rejects a nonsensical measured scale instead of applying it")
    func clampedRejectsNonsensicalInput() {
        for bad: CGFloat in [0, -1, .nan, .infinity] {
            #expect(isClose(PreviewInitialZoomPolicy.clamped(bad, kind: .raster),
                            PreviewInitialZoomPolicy.neutralScale))
            #expect(isClose(PreviewInitialZoomPolicy.clamped(bad, kind: .vector),
                            PreviewInitialZoomPolicy.neutralScale))
        }
    }

    @Test("Only raster declares an upper bound")
    func upperBoundIsRasterOnly() {
        #expect(PreviewInitialZoomPolicy.upperBound(for: .raster) == 1.0)
        #expect(PreviewInitialZoomPolicy.upperBound(for: .vector) == nil)
    }
}
