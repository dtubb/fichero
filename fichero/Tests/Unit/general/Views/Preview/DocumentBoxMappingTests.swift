@testable import Fichero
import CoreGraphics
import Testing

/// #5020 and #5142: boxes drawn in the scroll view's document view, moved by AppKit's one transform.
/// What breaks without these: a box drawn a flip or a zoom away from its words -- the "below and
/// right" of #5020 -- in the one layer that is meant to make that impossible.
struct DocumentBoxMappingTests {
    /// A 2,000 x 3,000 point page, as `ImageWithCursorTrackingMac` sizes the image view.
    private let page = CGSize(width: 2000, height: 3000)

    @Test("a box maps into the unflipped image view: x across, y measured up from the bottom")
    func mapsIntoTheDocument() throws {
        let rect = try #require(DocumentBoxMapping.rect(normalized: [0.1, 0.2, 0.3, 0.1], documentSize: page))
        #expect(rect == CGRect(x: 200, y: 2100, width: 600, height: 300))
    }

    @Test("a zero-size placeholder is never drawn")
    func placeholdersAreNotDrawn() {
        #expect(DocumentBoxMapping.rect(normalized: [0, 0, 0, 0], documentSize: page) == nil)
        #expect(DocumentBoxMapping.rect(normalized: [0.1, 0.1], documentSize: page) == nil)
    }

    /// The test #5020 asks for: at a zoom and a scroll that are NOT 1:1 (67 percent, scrolled right
    /// and down), the box AppKit shows lands where the POINTER path says the box is. The pointer path
    /// is the published `PreviewImageGeometry`, built here exactly as
    /// `ImageWithCursorTrackingCoordinator.updateVisibleRect` builds it.
    @Test("at 67 percent and scrolled, the drawn box and the clicked box are the same place")
    func documentPathAgreesWithThePointerPath() throws {
        let magnification: CGFloat = 0.67
        let clip = CGSize(width: 900, height: 700)                 // the pane, in screen points
        let visibleDoc = CGRect(x: 400, y: 1200,                   // scrolled right and down
                                width: clip.width / magnification, height: clip.height / magnification)
        let bbox = [0.3, 0.45, 0.1, 0.02]

        let doc = try #require(DocumentBoxMapping.rect(normalized: bbox, documentSize: page))
        let screen = DocumentBoxMapping.onScreen(
            documentRect: doc, documentVisibleRect: visibleDoc, magnification: magnification
        )

        let geometry = PreviewImageGeometry(
            visible: CGRect(
                x: visibleDoc.minX / page.width,
                y: 1 - visibleDoc.maxY / page.height,
                width: visibleDoc.width / page.width,
                height: visibleDoc.height / page.height
            ),
            drawnFrame: CGRect(origin: .zero, size: clip)
        )
        let centre = try #require(PreviewPointerMapping.normalized(
            panePoint: CGPoint(x: screen.midX, y: screen.midY), geometry: geometry
        ))
        #expect(abs(centre.x - (bbox[0] + bbox[2] / 2)) < 1e-9)
        #expect(abs(centre.y - (bbox[1] + bbox[3] / 2)) < 1e-9)
    }
}
