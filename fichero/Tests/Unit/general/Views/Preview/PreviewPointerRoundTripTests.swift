#if os(macOS)
import AppKit
@testable import Fichero
import XCTest

/// The markup bar's marquee, word-select and annotate bands are drawn by
/// mapping a mouse point IN to normalized image space and the resulting box
/// back OUT to the overlay. Those are two different pieces of code, and the
/// only thing that makes a band land under the pointer is that they are exact
/// inverses.
///
/// Daniel, 2026-09-03: the bands were "offset down and to the right" and the
/// marquee "feels bizarre and disconnected to the mouse pointer". The cause
/// was not a constant offset but a SCALE error: `DrawnImageFrame.compute`
/// framed the overlay to `scrollView.bounds` while `updateVisibleRect`
/// derived the normalized window from `documentVisibleRect`, which is clipped
/// to the CLIP VIEW. With legacy scrollers (the system's "Show scroll bars:
/// Always") those differ by ~17pt on each axis, so the band ran further from
/// the pointer the further it got from the top-left corner.
///
/// These tests drive real AppKit views through the same layout rules the
/// coordinator applies, then assert the round trip is the identity.
final class PreviewPointerRoundTripTests: XCTestCase {

    // MARK: - Harness

    /// A scroll view + image view laid out exactly as
    /// `ImageWithCursorTrackingMacCoordinator.centerContent` leaves them.
    @MainActor
    private struct Harness {
        let scrollView: NSScrollView
        let imageView: NSImageView

        init(imageSize: CGSize, pane: CGSize, magnification: CGFloat, scrollerStyle: NSScroller.Style) {
            let image = NSImage(size: imageSize)
            image.lockFocus()
            NSColor.red.setFill()
            NSRect(origin: .zero, size: imageSize).fill()
            image.unlockFocus()

            let imageView = NSImageView()
            imageView.image = image
            imageView.imageScaling = .scaleNone

            let scrollView = NSScrollView(frame: NSRect(origin: .zero, size: pane))
            scrollView.hasVerticalScroller = true
            scrollView.hasHorizontalScroller = true
            scrollView.scrollerStyle = scrollerStyle
            scrollView.automaticallyAdjustsContentInsets = false
            scrollView.allowsMagnification = true
            scrollView.minMagnification = 0.01
            scrollView.maxMagnification = 10
            scrollView.documentView = imageView
            scrollView.magnification = magnification

            self.scrollView = scrollView
            self.imageView = imageView
            layOut()
            scrollView.layoutSubtreeIfNeeded()
            layOut()
            scrollView.layoutSubtreeIfNeeded()
        }

        /// Mirrors `centerContent` / `updateContentInsetsForCurrentLayout`.
        func layOut() {
            guard let image = imageView.image else { return }
            let imageSize = image.size
            let viewSize = scrollView.contentSize
            let mag = scrollView.magnification
            let frameW = max(imageSize.width, viewSize.width / mag)
            let frameH = max(imageSize.height, viewSize.height / mag)
            let needsExpand = imageSize.width * mag < viewSize.width
                || imageSize.height * mag < viewSize.height
            imageView.frame = NSRect(origin: .zero, size: CGSize(width: frameW, height: frameH))
            imageView.imageAlignment = needsExpand ? .alignCenter : .alignTopLeft
            scrollView.contentInsets = NSEdgeInsets()
        }

        func scroll(to origin: CGPoint) {
            scrollView.contentView.scroll(to: origin)
            scrollView.reflectScrolledClipView(scrollView.contentView)
        }

        /// Mirrors `ImageWithCursorTrackingMacCoordinator.updateVisibleRect`.
        var normalizedVisible: CGRect {
            let visibleRect = scrollView.contentView.documentVisibleRect
            let imageSize = imageView.image?.size ?? .zero
            let width = min(1.0, visibleRect.width / imageSize.width)
            let height = min(1.0, visibleRect.height / imageSize.height)
            let originX = visibleRect.origin.x / imageSize.width
            let originY = 1.0 - (visibleRect.origin.y + visibleRect.height) / imageSize.height
            return CGRect(
                x: max(0, min(1 - width, originX)),
                y: max(0, min(1 - height, originY)),
                width: width, height: height
            )
        }

        /// The pointer transform from `ImageWithCursorTracking.makeImageView`:
        /// a point in the image view's own (bottom-left) space → normalized
        /// image point.
        func normalize(imageViewPoint point: CGPoint) -> CGPoint {
            let drawn = DrawnImageFrame.drawnRect(in: imageView)
            return CGPoint(
                x: (point.x - drawn.minX) / drawn.width,
                y: 1 - (point.y - drawn.minY) / drawn.height
            )
        }

        /// The overlay transform: normalized image point → a point in the
        /// SwiftUI overlay's space (which IS the scroll view's space).
        func overlayPoint(normalized point: CGPoint) -> CGPoint? {
            guard let frame = DrawnImageFrame.compute(scrollView: scrollView, imageView: imageView),
                  let rect = BoundingBoxGeometry.viewRect(
                      normalized: [point.x, point.y, 0, 0],
                      in: frame.size, visible: normalizedVisible
                  ) else { return nil }
            return CGPoint(x: rect.minX + frame.minX, y: rect.minY + frame.minY)
        }

        /// A pane point (SwiftUI top-left space) all the way there and back.
        func roundTrip(_ panePoint: CGPoint) -> CGPoint? {
            // `NSScrollView.isFlipped` is true, so the SwiftUI overlay's
            // top-left space and the scroll view's space are the same one.
            let inImageView = imageView.convert(panePoint, from: scrollView)
            return overlayPoint(normalized: normalize(imageViewPoint: inImageView))
        }
    }

    /// One layout under test — a named image size and magnification.
    private struct Layout {
        let label: String
        let image: CGSize
        let magnification: CGFloat
    }

    private static let probes = [
        CGPoint(x: 100, y: 100),
        CGPoint(x: 400, y: 300),
        CGPoint(x: 700, y: 500)
    ]

    @MainActor
    private func assertRoundTripIsIdentity(
        _ harness: Harness,
        _ label: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        for probe in Self.probes {
            guard let back = harness.roundTrip(probe) else {
                XCTFail("\(label): no drawn frame for \(probe)", file: file, line: line)
                continue
            }
            XCTAssertEqual(back.x, probe.x, accuracy: 0.5, "\(label) x", file: file, line: line)
            XCTAssertEqual(back.y, probe.y, accuracy: 0.5, "\(label) y", file: file, line: line)
        }
    }

    // MARK: - The regression itself

    /// The failing case before the fix: legacy scrollers make the clip view
    /// ~17pt smaller than the scroll view on both axes, and the band drifted
    /// down and to the right in proportion to the distance from the origin.
    @MainActor
    func testRoundTripIsIdentityWithLegacyScrollers() {
        let cases = [
            Layout(label: "portrait letterboxed at fit", image: CGSize(width: 1000, height: 2000), magnification: 0.3),
            Layout(label: "landscape letterboxed at fit", image: CGSize(width: 2000, height: 1000), magnification: 0.4),
            Layout(label: "zoomed in at 1x", image: CGSize(width: 2000, height: 3000), magnification: 1.0),
            Layout(label: "zoomed in at 2x", image: CGSize(width: 2000, height: 3000), magnification: 2.0),
            Layout(label: "wide page, vertical slack", image: CGSize(width: 3000, height: 400), magnification: 1.0)
        ]
        for layout in cases {
            let harness = Harness(
                imageSize: layout.image, pane: CGSize(width: 800, height: 600),
                magnification: layout.magnification, scrollerStyle: .legacy
            )
            assertRoundTripIsIdentity(harness, "legacy/\(layout.label)")
        }
    }

    /// Overlay scrollers were already correct; they must stay correct.
    @MainActor
    func testRoundTripIsIdentityWithOverlayScrollers() {
        let harness = Harness(
            imageSize: CGSize(width: 1000, height: 2000), pane: CGSize(width: 800, height: 600),
            magnification: 0.3, scrollerStyle: .overlay
        )
        assertRoundTripIsIdentity(harness, "overlay/portrait letterboxed")
    }

    /// Scrolled AND zoomed — the case where a stale or mis-sized viewport
    /// shows up as both an offset and a scale error.
    @MainActor
    func testRoundTripIsIdentityWhenScrolledAndZoomed() {
        for style in [NSScroller.Style.legacy, .overlay] {
            let harness = Harness(
                imageSize: CGSize(width: 2000, height: 3000), pane: CGSize(width: 800, height: 600),
                magnification: 2.0, scrollerStyle: style
            )
            harness.scroll(to: CGPoint(x: 500, y: 1200))
            assertRoundTripIsIdentity(harness, "scrolled+zoomed/\(style.rawValue)")
        }
    }

    /// The overlay must be framed to the CLIP VIEW, never to the scroll
    /// view's full bounds — that difference IS the bug.
    @MainActor
    func testDrawnFrameNeverExceedsTheClipView() {
        let harness = Harness(
            imageSize: CGSize(width: 2000, height: 3000), pane: CGSize(width: 800, height: 600),
            magnification: 1.0, scrollerStyle: .legacy
        )
        let content = harness.scrollView.contentSize
        guard let frame = DrawnImageFrame.compute(
            scrollView: harness.scrollView, imageView: harness.imageView
        ) else {
            return XCTFail("no drawn frame")
        }
        XCTAssertLessThanOrEqual(frame.width, content.width + 0.5)
        XCTAssertLessThanOrEqual(frame.height, content.height + 0.5)
    }

    // MARK: - The published-geometry authority (2026-09-04)

    /// The pointer normalizes through the SAME `PreviewImageGeometry` the
    /// overlay draws with (`PreviewPointerMapping`), so a click must land in
    /// the box it VISUALLY covers — the wrong-line-select regression: the
    /// old image-view-space derivation could disagree with the drawn overlay
    /// while this file's isolated round trips all passed.
    @MainActor
    private func assertClickHitsTheBoxItCovers(
        _ harness: Harness,
        _ label: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        guard let frame = DrawnImageFrame.compute(
            scrollView: harness.scrollView, imageView: harness.imageView
        ) else {
            return XCTFail("\(label): no drawn frame", file: file, line: line)
        }
        let geometry = PreviewImageGeometry(visible: harness.normalizedVisible, drawnFrame: frame)
        // Top row, middle, bottom row — the shape of a page of text lines.
        let boxes: [[Double]] = [
            [0.20, 0.05, 0.60, 0.04],
            [0.20, 0.48, 0.60, 0.04],
            [0.20, 0.91, 0.60, 0.04]
        ]
        for (index, box) in boxes.enumerated() {
            guard let rect = BoundingBoxGeometry.viewRect(
                normalized: box, in: frame.size, visible: geometry.visible
            ) else { continue }
            let paneCenter = CGPoint(x: frame.minX + rect.midX, y: frame.minY + rect.midY)
            // Off-screen boxes (zoomed in) are not clickable — skip honestly.
            guard paneCenter.x >= 0, paneCenter.y >= 0 else { continue }
            guard let normalized = PreviewPointerMapping.normalized(
                panePoint: paneCenter, geometry: geometry
            ) else {
                XCTFail("\(label): unmeasured geometry", file: file, line: line)
                continue
            }
            // The region layer's inverse: normalized → overlay-local point.
            let layerPoint = CGPoint(
                x: (normalized.x - geometry.visible.minX) / geometry.visible.width * frame.width,
                y: (normalized.y - geometry.visible.minY) / geometry.visible.height * frame.height
            )
            let picked = RegionHitTesting.pick(
                at: layerPoint, boxes: boxes, in: frame.size, visible: geometry.visible
            )
            XCTAssertEqual(
                picked, index,
                "\(label): the click at box \(index)'s visual center must select box \(index)",
                file: file, line: line
            )
        }
    }

    @MainActor
    func testClickHitsTheBoxItVisuallyCovers() {
        let cases = [
            Layout(label: "letterboxed at fit", image: CGSize(width: 1000, height: 2000), magnification: 0.3),
            Layout(label: "wide page at fit", image: CGSize(width: 2000, height: 1000), magnification: 0.4),
            Layout(label: "zoomed to 1x", image: CGSize(width: 1000, height: 2000), magnification: 1.0)
        ]
        for style in [NSScroller.Style.legacy, .overlay] {
            for layout in cases {
                let harness = Harness(
                    imageSize: layout.image, pane: CGSize(width: 800, height: 600),
                    magnification: layout.magnification, scrollerStyle: style
                )
                assertClickHitsTheBoxItCovers(harness, "\(style.rawValue)/\(layout.label)")
            }
        }
    }

    @MainActor
    func testClickHitsTheBoxItCoversWhenScrolledAndZoomed() {
        let harness = Harness(
            imageSize: CGSize(width: 2000, height: 3000), pane: CGSize(width: 800, height: 600),
            magnification: 1.5, scrollerStyle: .legacy
        )
        harness.scroll(to: CGPoint(x: 600, y: 1300))
        assertClickHitsTheBoxItCovers(harness, "scrolled+zoomed")
    }

    /// The retired image-view derivation and the published mapping agree in a
    /// correctly laid-out harness — the baseline the runtime tripwire
    /// (`pointer-triage`) measures divergence against.
    @MainActor
    func testPublishedMappingAgreesWithTheImageViewDerivation() {
        for layout in [
            Layout(label: "fit", image: CGSize(width: 1000, height: 2000), magnification: 0.3),
            Layout(label: "zoomed", image: CGSize(width: 2000, height: 3000), magnification: 2.0)
        ] {
            let harness = Harness(
                imageSize: layout.image, pane: CGSize(width: 800, height: 600),
                magnification: layout.magnification, scrollerStyle: .legacy
            )
            guard let frame = DrawnImageFrame.compute(
                scrollView: harness.scrollView, imageView: harness.imageView
            ) else { return XCTFail("\(layout.label): no drawn frame") }
            let geometry = PreviewImageGeometry(visible: harness.normalizedVisible, drawnFrame: frame)
            for probe in Self.probes {
                let inImageView = harness.imageView.convert(probe, from: harness.scrollView)
                let legacy = harness.normalize(imageViewPoint: inImageView)
                guard let published = PreviewPointerMapping.normalized(
                    panePoint: probe, geometry: geometry
                ) else { return XCTFail("\(layout.label): unmeasured") }
                XCTAssertEqual(published.x, legacy.x, accuracy: 0.002, "\(layout.label) x for \(probe)")
                XCTAssertEqual(published.y, legacy.y, accuracy: 0.002, "\(layout.label) y for \(probe)")
            }
        }
    }

    // MARK: - The shared drawn-image rule

    /// `drawnRect` is the single rule both halves use; it must follow the
    /// image view's own scaling mode rather than assume `.scaleNone`.
    @MainActor
    func testDrawnRectFollowsTheImageViewScalingMode() {
        let harness = Harness(
            imageSize: CGSize(width: 1000, height: 2000), pane: CGSize(width: 800, height: 600),
            magnification: 0.3, scrollerStyle: .overlay
        )
        let native = DrawnImageFrame.drawnRect(in: harness.imageView)
        XCTAssertEqual(native.width, 1000, accuracy: 0.5)
        XCTAssertEqual(native.height, 2000, accuracy: 0.5)

        harness.imageView.imageScaling = .scaleProportionallyUpOrDown
        let fitted = DrawnImageFrame.drawnRect(in: harness.imageView)
        let expected = DrawnImageFrame.aspectFitRect(
            of: CGSize(width: 1000, height: 2000), in: harness.imageView.bounds
        )
        XCTAssertEqual(fitted, expected)
    }
}
#endif
