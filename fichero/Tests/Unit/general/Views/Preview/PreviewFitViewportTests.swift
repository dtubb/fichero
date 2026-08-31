import Foundation
@testable import Fichero
import Testing

#if os(macOS)
import AppKit
#endif

/// The preview's fit/layout math must size the document to the scroll view's
/// CONTENT size, never its bounds (Daniel, 2026-08-31: pinch/pan/swipes and
/// "scroll bars at fit" all dead at once).
///
/// With "Show scroll bars: Always" the scrollers are LEGACY and `contentSize`
/// is `bounds` minus the scroller thickness. Sizing to bounds made every fitted
/// image overflow by ~15px on both axes: permanent scrollbars at fit, and
/// `SiblingSwipeScrollView`'s pan-first grammar (which compares against
/// contentSize) never yielded to page/rendition swipes.
struct PreviewFitViewportTests {
    private func source(_ relative: String) throws -> String {
        let url = try AppSource.root().appendingPathComponent(relative)
        return try String(contentsOf: url, encoding: .utf8)
    }

    @Test("fit and layout sites read contentSize, not bounds")
    func layoutSitesUseContentSize() throws {
        for file in [
            "Views/Preview/ImageViewer/CursorTracking/ImageWithCursorTrackingMac.swift",
            "Views/Preview/ImageViewer/CursorTracking/ImageWithCursorTrackingMacCoordinator.swift"
        ] {
            let text = try source(file)
            #expect(
                !text.contains("let viewSize = scrollView.bounds.size"),
                "\(file): document frame must be sized to contentSize"
            )
            #expect(
                !text.contains("paneSize: scrollView.bounds.size"),
                "\(file): fit scale must be computed against contentSize"
            )
        }
    }

    #if os(macOS)
    @Test("a fitted document never overflows legacy-scroller content size")
    @MainActor
    func fittedDocumentFillsContentExactly() {
        let scrollView = NSScrollView(frame: NSRect(x: 0, y: 0, width: 400, height: 300))
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = true
        scrollView.scrollerStyle = .legacy
        scrollView.allowsMagnification = true
        let image = CGSize(width: 1000, height: 1500)
        let content = scrollView.contentSize
        // Legacy scrollers eat real room — the premise of the bug.
        #expect(content.width < scrollView.bounds.width || content.height < scrollView.bounds.height)

        let fit = PreviewInitialZoomPolicy.fitScale(contentSize: image, paneSize: content)!
        // The same expansion `layoutImageView` performs, against contentSize.
        let frame = CGSize(
            width: max(image.width, content.width / fit),
            height: max(image.height, content.height / fit)
        )
        // SiblingSwipeScrollView's pan test: scaled document vs contentSize.
        #expect(frame.width * fit <= content.width + 0.5)
        #expect(frame.height * fit <= content.height + 0.5)

        // Sizing to BOUNDS instead is exactly the defect: it overflows.
        let wrong = CGSize(
            width: max(image.width, scrollView.bounds.width / fit),
            height: max(image.height, scrollView.bounds.height / fit)
        )
        #expect(wrong.width * fit > content.width + 0.5 || wrong.height * fit > content.height + 0.5)
    }
    #endif
}
