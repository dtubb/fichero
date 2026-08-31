#if canImport(AppKit)
import AppKit
import OSLog

// MARK: - Coordinator

/// Coordinator for macOS NSViewRepresentable image viewer with cursor tracking and loupe
class ImageWithCursorTrackingMacCoordinator: NSObject, NSGestureRecognizerDelegate {
    static let logger = Logger(subsystem: "app.fichero.fichero", category: "ImageWithCursorTracking")

    var scrollView: NSScrollView?
    var imageView: NSView?
    var currentURL: URL?
    /// Monotonic token for async image loads (#3864): each `loadImageAsync` bumps
    /// it, and a completing decode applies only if it's still the latest — so a
    /// fast page-flip drops the superseded decode instead of flashing it in.
    var imageLoadToken = 0
    func beginImageLoad() -> Int {
        imageLoadToken += 1
        return imageLoadToken
    }
    func isCurrentImageLoad(_ token: Int) -> Bool { token == imageLoadToken }
    /// Tracks the last override image set so we detect changes by identity (#1402).
    weak var currentOverrideImage: NSImage?
    /// Item identity for the same-item-vs-new-item call in
    /// `applyImageChangeIfNeeded` — `currentURL` is nil throughout rendered
    /// mode, so it cannot make that call.
    var currentItemKey: String?
    /// Visible window AND drawn image rect from ONE measurement pass.
    ///
    /// One callback, not two (2026-08-20 bbox review, D3): overlays frame to
    /// `drawnFrame` while mapping boxes through `visible`, so a consumer that
    /// sees a fresh value of one against a stale value of the other draws
    /// every box in the wrong place. Two callbacks meant two independent
    /// `@MainActor` hops, and exactly that mismatch during a pinch.
    var onGeometryChanged: ((PreviewImageGeometry) -> Void)?
    /// #596 (2nd attempt): fires once at gesture `.ended` with the final
    /// magnification. The owning `ImageWithCursorTracking` writes it
    /// back to its `@Binding var scale` so `updateNSView`'s sync-check
    /// sees matching values and doesn't reset magnification on the next
    /// redraw. The first attempt (commit `fc01d393`, reverted in
    /// `8eeabee3`) fired this on every `boundsDidChange`, which raced
    /// with `updateNSView` during active gestures and broke pinch
    /// entirely (#599).
    var onScaleChanged: ((CGFloat) -> Void)?
    /// True while the user is actively pinching. `updateNSView`'s
    /// sync-check (line 138-140) is skipped while this is set so the
    /// scroll view's magnification isn't reverted mid-gesture.
    var isUserMagnifying: Bool = false
    var magnifyGesture: NSMagnificationGestureRecognizer?
    var doubleClickGesture: NSClickGestureRecognizer?
    var onZoomIn: (() -> Void)?
    var needsInitialCenter: Bool = false
    var initialMagnification: CGFloat = 1.0

    @MainActor
    @objc func boundsDidChange(_ notification: Notification) {
        revealAfterInitialLayoutIfNeeded()
        updateContentInsetsForCurrentLayout()
        updateVisibleRect()
    }

    /// `makeNSView` hides the scroll view until the first center/fit pass
    /// to avoid a flash at 1x. In split-pane layouts SwiftUI can mount the
    /// AppKit view at zero size, then deliver the real size only through a
    /// bounds-change notification. Without revealing from that path the
    /// loaded image remains invisible even though storage returned it.
    @MainActor
    func revealAfterInitialLayoutIfNeeded() {
        guard needsInitialCenter,
              let scrollView = scrollView,
              scrollView.bounds.width > 0,
              scrollView.bounds.height > 0,
              let imageView = imageView as? NSImageView,
              imageView.image != nil else { return }

        needsInitialCenter = false
        if let fitScale = calculateFitScale() {
            scrollView.magnification = fitScale
            noteAutoFitApplied()
            onScaleChanged?(fitScale)
        }
        centerContent()
        if scrollView.alphaValue < 1 {
            scrollView.alphaValue = 1
        }
    }

    @MainActor
    private func updateContentInsetsForCurrentLayout() {
        guard let scrollView = scrollView,
              let imgView = imageView as? NSImageView,
              let image = imgView.image else { return }

        let imageSize = image.size
        // contentSize, NOT bounds (2026-08-31): with "Show scroll bars:
        // Always" (legacy scrollers) contentSize is the bounds minus the
        // scroller thickness. Sizing the document to bounds made every
        // fitted image "overflow" by ~15px on BOTH axes — permanent
        // scrollbars at fit, and SiblingSwipeScrollView's pan-first grammar
        // (which compares against contentSize) never yielded to page/
        // rendition swipes. Every fit/layout site must use contentSize.
        let viewSize = scrollView.contentSize
        let mag = scrollView.magnification
        let scaledW = imageSize.width * mag
        let scaledH = imageSize.height * mag

        let frameW = max(imageSize.width, viewSize.width / mag)
        let frameH = max(imageSize.height, viewSize.height / mag)
        let needsExpand = scaledW < viewSize.width || scaledH < viewSize.height
        let targetFrame = NSRect(origin: .zero, size: CGSize(width: frameW, height: frameH))

        if imgView.frame != targetFrame {
            imgView.frame = targetFrame
        }
        imgView.imageAlignment = needsExpand ? .alignCenter : .alignTopLeft
        scrollView.contentInsets = NSEdgeInsets()
    }

    // Allow our gesture recognizer to work simultaneously with NSScrollView's built-in magnification
    func gestureRecognizer(_ gestureRecognizer: NSGestureRecognizer,
                           shouldRecognizeSimultaneouslyWith otherGestureRecognizer: NSGestureRecognizer) -> Bool {
        return true
    }

    @MainActor
    @objc func handleDoubleClick(_ gesture: NSClickGestureRecognizer) {
        guard let scrollView = scrollView else { return }

        if gesture.state == .ended {
            // A deliberate zoom — stop auto-fitting on resize (#4279).
            markManualZoom()
            // Get click location for zoom centering
            let clickLocation = gesture.location(in: scrollView)

            // Toggle between zooming in and fit to window
            if scrollView.magnification > 1.1 {
                // Currently zoomed in - fit to window
                scrollView.magnification = 1.0
            } else {
                // Currently at fit - zoom in to 2x at click location
                scrollView.setMagnification(2.0, centeredAt: clickLocation)
            }
        }
    }

    /// Zoom so a normalized image rect fills the viewport (entry ladder,
    /// 2026-08-23: "we should only show the bounding box"). Magnification is
    /// chosen so the rect plus a small margin fits both axes, clamped to the
    /// scroll view's own limits, then the rect is centered. The margin keeps
    /// a sliver of page visible around the band so the crop reads as a place
    /// ON the page, not a detached scan.
    @MainActor
    func zoomToNormalizedRegion(_ rect: [Double]) {
        guard rect.count == 4, rect[2] > 0, rect[3] > 0,
              let scrollView = scrollView,
              let imageView = imageView as? NSImageView,
              let image = imageView.image else { return }
        let imageSize = image.size
        let regionWidth = rect[2] * imageSize.width
        let regionHeight = rect[3] * imageSize.height
        let viewport = scrollView.contentSize
        guard viewport.width > 0, viewport.height > 0 else { return }
        let margin: CGFloat = 1.12
        let target = min(
            viewport.width / (regionWidth * margin),
            viewport.height / (regionHeight * margin)
        )
        let clamped = min(max(target, scrollView.minMagnification), scrollView.maxMagnification)
        scrollView.magnification = clamped
        // Center of the region, top-left-normalized → the scroll origin that
        // centers it in the viewport (document coords, bottom-left origin).
        let centerX = (rect[0] + rect[2] / 2) * imageSize.width
        let centerYTop = (rect[1] + rect[3] / 2) * imageSize.height
        let visible = scrollView.contentView.documentVisibleRect
        let origin = CGPoint(
            x: centerX - visible.width / 2,
            y: (imageSize.height - centerYTop) - visible.height / 2
        )
        scrollView.contentView.scroll(to: origin)
        scrollView.reflectScrolledClipView(scrollView.contentView)
        updateVisibleRect()
    }

    /// Scroll to a normalized position (0-1 coordinates)
    @MainActor
    func scrollToNormalizedPosition(_ normalizedOrigin: CGPoint) {
        guard let scrollView = scrollView,
              let imageView = imageView as? NSImageView,
              let image = imageView.image else { return }

        // Convert normalized position to document (image) coordinates
        // normalizedOrigin is the top-left corner in normalized space (0-1, top-left origin)
        let imageSize = image.size

        // X: No flip needed (both use left-to-right)
        let docX = normalizedOrigin.x * imageSize.width

        // Y: Flip back (minimap top → NSScrollView bottom)
        // We need the visible height in document coordinates
        let visibleHeightInDocCoords = scrollView.contentView.documentVisibleRect.height
        let docY = (1.0 - normalizedOrigin.y) * imageSize.height - visibleHeightInDocCoords

        let targetPoint = CGPoint(x: docX, y: docY)
        scrollView.contentView.scroll(to: targetPoint)
        scrollView.reflectScrolledClipView(scrollView.contentView)
    }

    @MainActor
    func updateVisibleRect() {
        guard let scrollView = scrollView,
              let imageView = imageView as? NSImageView,
              let image = imageView.image else { return }

        // documentVisibleRect is in document (image) coordinates, not screen coordinates
        // So we normalize against the image size, not the scaled/displayed size
        let visibleRect = scrollView.contentView.documentVisibleRect
        let imageSize = image.size

        // Calculate normalized visible rect (0-1 range) using image size
        let normalizedWidth = min(1.0, visibleRect.width / imageSize.width)
        let normalizedHeight = min(1.0, visibleRect.height / imageSize.height)

        // NSScrollView coordinate system vs Minimap:
        // - X: Both use left-to-right, no flip needed
        // - Y: NSScrollView uses bottom-left origin (Y up), minimap uses top-left (Y down)

        // X: No flip needed
        let normalizedX = visibleRect.origin.x / imageSize.width

        // Flip Y: The TOP edge in NSScrollView should map to TOP edge in minimap
        let normalizedY = 1.0 - (visibleRect.origin.y + visibleRect.height) / imageSize.height

        let rect = CGRect(
            x: max(0, min(1 - normalizedWidth, normalizedX)),
            y: max(0, min(1 - normalizedHeight, normalizedY)),
            width: normalizedWidth,
            height: normalizedHeight
        )

        // Both rects leave together or not at all. Publishing the visible
        // window while `DrawnImageFrame.compute` returns nil would strand the
        // consumer with a fresh crop and a stale (or zero) frame — the D3
        // mismatch, just arriving by a different route.
        guard let drawn = DrawnImageFrame.compute(scrollView: scrollView, imageView: imageView) else {
            return
        }
        onGeometryChanged?(PreviewImageGeometry(visible: rect, drawnFrame: drawn))
    }

    /// Calculate the scale needed to fit the image in the scroll view.
    /// The rule itself lives in `PreviewInitialZoomPolicy` so the image and PDF
    /// surfaces open the same way (#4279); `nil` means "not measurable yet".
    @MainActor
    func calculateFitScale() -> CGFloat? {
        guard let scrollView = scrollView,
              let imageView = imageView as? NSImageView,
              let image = imageView.image,
              let fit = PreviewInitialZoomPolicy.fitScale(
                  contentSize: image.size,
                  // contentSize, not bounds — legacy scrollers (see
                  // updateContentInsetsForCurrentLayout, 2026-08-31).
                  paneSize: scrollView.contentSize
              ) else { return nil }

        return PreviewInitialZoomPolicy.clamped(fit, kind: .raster)
    }

    // MARK: - Zoom Ownership (#4279)

    /// True once the user has taken manual control of the zoom — a pinch, a
    /// double-click, or a toolbar/keyboard zoom command. While it is false the
    /// preview keeps re-fitting to the pane as the pane resizes; once true the
    /// scale is frozen until a different item is displayed.
    var userHasZoomedManually = false

    /// Pane size the last automatic fit was computed for, so a genuine resize
    /// can be told apart from an ordinary layout pass.
    private var lastAutoFitPaneSize: CGSize = .zero

    /// The user just took over the zoom — stop auto-fitting.
    func markManualZoom() {
        userHasZoomedManually = true
    }

    /// A magnification this code just set programmatically, written BEFORE the
    /// `scale` binding's Task write has landed (2026-08-11, hi-res swap): the
    /// magnification↔scale sync in `updateNSView` must WAIT for the binding to
    /// catch up, or it re-asserts the stale scale and snaps the view — the
    /// "first pinch zooms out again" defect.
    var pendingProgrammaticScale: CGFloat?

    /// True when the sync may run: no pending programmatic scale, or the
    /// binding has caught up (which also clears the pending value).
    func consumePendingScaleIfMatched(_ bindingScale: CGFloat) -> Bool {
        guard let pending = pendingProgrammaticScale else { return true }
        if abs(bindingScale - pending) <= 0.01 {
            pendingProgrammaticScale = nil
            return true
        }
        return false
    }

    /// A new item is on screen — hand the zoom back to the automatic fit.
    func resetZoomOwnershipForNewItem() {
        userHasZoomedManually = false
        lastAutoFitPaneSize = .zero
    }

    /// Record that an automatic fit has just been applied at the pane's
    /// current size, so the next pass doesn't treat it as a resize.
    @MainActor
    func noteAutoFitApplied() {
        lastAutoFitPaneSize = scrollView?.contentSize ?? .zero
    }

    /// The scale to re-fit to because the pane resized and the user hasn't
    /// taken over, or `nil` when nothing should change.
    @MainActor
    func autoRefitScale() -> CGFloat? {
        guard !userHasZoomedManually, let scrollView = scrollView else { return nil }
        let paneSize = scrollView.contentSize
        // Sub-point jitter is layout noise, not a resize.
        guard abs(paneSize.width - lastAutoFitPaneSize.width) > 0.5
                || abs(paneSize.height - lastAutoFitPaneSize.height) > 0.5,
              let fit = calculateFitScale() else { return nil }
        lastAutoFitPaneSize = paneSize
        return fit
    }

    /// Center the content in the scroll view using frame expansion + imageAlignment.
    @MainActor
    func centerContent() {
        guard let scrollView = scrollView,
              let imgView = imageView as? NSImageView,
              let image = imgView.image else { return }

        let imageSize = image.size
        // contentSize, not bounds — legacy scrollers (see
        // updateContentInsetsForCurrentLayout, 2026-08-31).
        let viewSize = scrollView.contentSize
        let mag = scrollView.magnification
        let scaledW = imageSize.width * mag
        let scaledH = imageSize.height * mag

        let frameW = max(imageSize.width, viewSize.width / mag)
        let frameH = max(imageSize.height, viewSize.height / mag)
        let needsExpand = scaledW < viewSize.width || scaledH < viewSize.height

        imgView.frame = NSRect(origin: .zero, size: CGSize(width: frameW, height: frameH))
        imgView.imageAlignment = needsExpand ? .alignCenter : .alignTopLeft
        scrollView.contentInsets = NSEdgeInsets()

        // Scroll to origin to show centered content
        scrollView.contentView.scroll(to: .zero)
        scrollView.reflectScrolledClipView(scrollView.contentView)
    }

    /// Pan the visible area by a relative number of points in document coordinates.
    @MainActor
    func panBy(x deltaX: CGFloat, y deltaY: CGFloat) {
        guard let scrollView = scrollView,
              let imageView = imageView as? NSImageView,
              let image = imageView.image else { return }

        let visibleRect = scrollView.contentView.documentVisibleRect
        let maxX = max(0, image.size.width - visibleRect.width)
        let maxY = max(0, image.size.height - visibleRect.height)

        let targetX = min(max(0, visibleRect.origin.x + deltaX), maxX)
        let targetY = min(max(0, visibleRect.origin.y + deltaY), maxY)

        scrollView.contentView.scroll(to: CGPoint(x: targetX, y: targetY))
        scrollView.reflectScrolledClipView(scrollView.contentView)
    }
}

// Make Coordinator available as ImageWithCursorTracking.Coordinator for API compatibility
extension ImageWithCursorTracking {
    typealias Coordinator = ImageWithCursorTrackingMacCoordinator
}
#endif
