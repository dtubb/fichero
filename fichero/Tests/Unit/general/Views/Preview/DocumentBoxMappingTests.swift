#if os(macOS)
@testable import Fichero
import CoreGraphics
import Testing

/// #5020: a segment's box -- and its highlight -- sits EXACTLY where the segment is on the page, at
/// every zoom and scroll. Three things must be one place (the maintainer, 2026-09-27):
///   the DRAWN rect  (the document overlay: `DocumentBoxMapping` inside the image view, moved by
///                    AppKit's transform),
///   the HIT rect    (the pointer path: `PreviewPointerMapping` through the published geometry),
///   the PAGE rect   (the segment's own image rect x magnification - clip origin, derived here
///                    independently, in top-left coordinates).
/// Across 50, 67, 95, 100 and 200 percent, below fit (centred on both axes), fit on one axis only,
/// and two page shapes -- the page itself and a landscape rendition of different pixel size.
/// What breaks without it: a highlight a letterbox, a flip or a zoom away from its words.
struct DocumentBoxMappingTests {
    private let clip = CGSize(width: 900, height: 700)
    private let boxes: [[Double]] = [[0.1, 0.2, 0.3, 0.1], [0.62, 0.71, 0.2, 0.04], [0.0, 0.0, 0.05, 0.05]]

    private struct Case {
        let page: CGSize
        let magnification: CGFloat
    }

    private var cases: [Case] {
        let pages = [CGSize(width: 2000, height: 3000), CGSize(width: 2200, height: 1466)]
        let zooms: [CGFloat] = [0.5, 0.67, 0.95, 1.0, 2.0, 0.2, 0.25]  // 0.2 below fit; 0.25 one axis
        return pages.flatMap { page in zooms.map { Case(page: page, magnification: $0) } }
    }

    /// The document view's bounds, as `updateContentInsets` sizes them: never smaller than the clip
    /// divided by the magnification, so a page zoomed out below fit is centred inside a larger view.
    private func documentBounds(_ c: Case) -> CGSize {
        CGSize(width: max(c.page.width, clip.width / c.magnification),
               height: max(c.page.height, clip.height / c.magnification))
    }

    /// The visible window, scrolled 35 percent of the way across and down where it can scroll.
    private func visibleTopLeft(_ c: Case) -> CGRect {
        let bounds = documentBounds(c)
        let size = CGSize(width: clip.width / c.magnification, height: clip.height / c.magnification)
        return CGRect(x: max(0, bounds.width - size.width) * 0.35,
                      y: max(0, bounds.height - size.height) * 0.35,
                      width: size.width, height: size.height)
    }

    /// The same window in the unflipped document space AppKit uses.
    private func visibleDocument(_ c: Case) -> CGRect {
        let topLeft = visibleTopLeft(c)
        return CGRect(x: topLeft.minX, y: documentBounds(c).height - topLeft.maxY,
                      width: topLeft.width, height: topLeft.height)
    }

    private func imageRect(_ c: Case) -> CGRect {
        DrawnImageFrame.centeredNativeRect(of: c.page, in: CGRect(origin: .zero, size: documentBounds(c)))
    }

    /// The published geometry, built as `updateVisibleRect` and `DrawnImageFrame.compute` build it.
    private func geometry(_ c: Case) -> PreviewImageGeometry {
        let visible = visibleDocument(c)
        let width = min(1, visible.width / c.page.width)
        let height = min(1, visible.height / c.page.height)
        let normalized = CGRect(
            x: max(0, min(1 - width, visible.minX / c.page.width)),
            y: max(0, min(1 - height, 1 - visible.maxY / c.page.height)),
            width: width, height: height
        )
        let imageOnScreen = DocumentBoxMapping.onScreen(
            documentRect: imageRect(c), documentVisibleRect: visible, magnification: c.magnification
        )
        let drawn = imageOnScreen.intersection(CGRect(origin: .zero, size: clip))
        return PreviewImageGeometry(visible: normalized, drawnFrame: drawn)
    }

    private func close(_ a: CGFloat, _ b: CGFloat) -> Bool { abs(a - b) < 1e-6 }

    @Test("drawn rect == page rect x magnification - clip origin, at every zoom and page shape")
    func drawnEqualsThePageRect() throws {
        for c in cases {
            let image = imageRect(c)
            let visibleTL = visibleTopLeft(c)
            let imageTopLeft = CGPoint(x: image.minX, y: documentBounds(c).height - image.maxY)
            for bbox in boxes {
                let doc = try #require(DocumentBoxMapping.rect(normalized: bbox, imageRect: image))
                let drawn = DocumentBoxMapping.onScreen(
                    documentRect: doc, documentVisibleRect: visibleDocument(c), magnification: c.magnification
                )
                // Independently: the box's top-left on the page, in top-left space, then the transform.
                let left = (imageTopLeft.x + bbox[0] * c.page.width - visibleTL.minX) * c.magnification
                let top = (imageTopLeft.y + bbox[1] * c.page.height - visibleTL.minY) * c.magnification
                #expect(close(drawn.minX, left), "x at \(c.magnification) on \(c.page)")
                #expect(close(drawn.minY, top), "y at \(c.magnification) on \(c.page)")
                #expect(close(drawn.width, bbox[2] * c.page.width * c.magnification))
                #expect(close(drawn.height, bbox[3] * c.page.height * c.magnification))
            }
        }
    }

    @Test("the pointer path hits the drawn rect's corners at the box's own corners, at every zoom")
    func hitEqualsDrawn() throws {
        for c in cases {
            let geometry = geometry(c)
            for bbox in boxes {
                let doc = try #require(DocumentBoxMapping.rect(normalized: bbox, imageRect: imageRect(c)))
                let drawn = DocumentBoxMapping.onScreen(
                    documentRect: doc, documentVisibleRect: visibleDocument(c), magnification: c.magnification
                )
                let topLeft = try #require(PreviewPointerMapping.normalized(
                    panePoint: CGPoint(x: drawn.minX, y: drawn.minY), geometry: geometry))
                let bottomRight = try #require(PreviewPointerMapping.normalized(
                    panePoint: CGPoint(x: drawn.maxX, y: drawn.maxY), geometry: geometry))
                #expect(close(topLeft.x, bbox[0]) && close(topLeft.y, bbox[1]),
                        "top-left at \(c.magnification) on \(c.page)")
                #expect(close(bottomRight.x, bbox[0] + bbox[2]) && close(bottomRight.y, bbox[1] + bbox[3]),
                        "bottom-right at \(c.magnification) on \(c.page)")
            }
        }
    }

    @Test("a zero-size placeholder is never drawn")
    func placeholdersAreNotDrawn() {
        let page = CGRect(x: 0, y: 0, width: 2000, height: 3000)
        #expect(DocumentBoxMapping.rect(normalized: [0, 0, 0, 0], imageRect: page) == nil)
        #expect(DocumentBoxMapping.rect(normalized: [0.1, 0.1], imageRect: page) == nil)
    }
}
#endif
