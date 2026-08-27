#if os(macOS)
@testable import Fichero
import Testing

// Daniel, 2026-08-23: "background removed is the best one, so default to
// that"; and the reader's current KIND survives sibling steps — "if I'm in
// background removed, I see that as I go left and right".
struct PreferredRenditionTests {
    private func rendition(_ role: String) -> DocumentRendition {
        DocumentRendition(
            id: "r-\(role)", documentId: "doc-1", role: role,
            path: "/\(role).jpg", isPrimary: role == "original",
            pixelWidth: nil, pixelHeight: nil,
            isMaterialized: true, hasOwnFrame: false, note: nil
        )
    }

    @Test("sticky role outranks the quality ranking")
    func stickyWins() {
        let list = [rendition("original"), rendition("background_removed"), rendition("enhanced")]
        #expect(preferredRenditionIndex(in: list, stickyRole: "enhanced") == 2)
    }

    @Test("no sticky: background removed beats enhanced beats original")
    func rankingOrder() {
        let all = [rendition("original"), rendition("enhanced"), rendition("background_removed")]
        #expect(preferredRenditionIndex(in: all, stickyRole: nil) == 2)
        let noBg = [rendition("original"), rendition("enhanced")]
        #expect(preferredRenditionIndex(in: noBg, stickyRole: nil) == 1)
    }

    @Test("a sticky kind the page lacks falls back to the ranking, then engine order")
    func stickyFallback() {
        let list = [rendition("original"), rendition("enhanced")]
        #expect(preferredRenditionIndex(in: list, stickyRole: "background_removed") == 1)
        #expect(preferredRenditionIndex(in: [rendition("original")], stickyRole: "svg") == 0)
        #expect(preferredRenditionIndex(in: [], stickyRole: nil) == 0)
    }
}

// The overlay frame matrix — match-or-skip, never transform (2026-08-23).
// Pins the reasoning from the entry-scoped-runs contract: a region node's
// BASE display is its parent's pixels, so a crop-framed set must stay dark
// there and light only on the crop rendition itself.
struct OverlayFrameMatrixTests {
    @Test("document-frame sets draw on the base image and frame-keeping renditions only")
    func nilRequired() {
        #expect(overlayFrameMatches(required: nil, displayed: nil, displayedHasOwnFrame: false))
        #expect(overlayFrameMatches(required: nil, displayed: "bg", displayedHasOwnFrame: false))
        #expect(!overlayFrameMatches(required: nil, displayed: "crop", displayedHasOwnFrame: true))
    }

    @Test("a named set draws only on exactly that rendition's pixels")
    func namedRequired() {
        #expect(overlayFrameMatches(required: "crop", displayed: "crop", displayedHasOwnFrame: true))
        // The region node's base display = parent's full pixels → dark.
        #expect(!overlayFrameMatches(required: "crop", displayed: nil, displayedHasOwnFrame: false))
        #expect(!overlayFrameMatches(required: "crop", displayed: "bg", displayedHasOwnFrame: false))
    }
}
#endif
