#if canImport(UIKit)
import OSLog
import UIKit

/// Coordinator for iOS UIViewRepresentable image viewer with zoom/pan support
@MainActor
final class ImageWithCursorTrackingIOSCoordinator: NSObject, UIScrollViewDelegate {
    static let logger = Logger(subsystem: "app.fichero.fichero", category: "ImageWithCursorTracking")

    var owner: ImageWithCursorTracking
    weak var scrollView: UIScrollView?
    weak var imageView: UIView?
    var currentURL: URL?
    /// Monotonic token for async image loads (#3864) — a completing decode applies
    /// only if it's still the latest, so a fast page-flip drops the stale one.
    var imageLoadToken = 0
    func beginImageLoad() -> Int {
        imageLoadToken += 1
        return imageLoadToken
    }
    func isCurrentImageLoad(_ token: Int) -> Bool { token == imageLoadToken }
    weak var currentOverrideImage: PlatformImage?
    var onVisibleRectChanged: ((CGRect) -> Void)?
    var onScaleChanged: ((CGFloat) -> Void)?
    var needsInitialCenter: Bool = false
    /// True while the user is actively pinching. Skips the binding-sync
    /// in `updateUIView` so the scroll view's zoom isn't reverted mid-gesture.
    var isUserMagnifying: Bool = false

    init(owner: ImageWithCursorTracking) {
        self.owner = owner
    }

    func viewForZooming(in scrollView: UIScrollView) -> UIView? {
        return imageView
    }

    func scrollViewWillBeginZooming(_ scrollView: UIScrollView, with view: UIView?) {
        isUserMagnifying = true
        // A pinch hands zoom control to the user (#4279).
        markManualZoom()
    }

    func scrollViewDidZoom(_ scrollView: UIScrollView) {
        centerContent()
        updateVisibleRect()
        onScaleChanged?(scrollView.zoomScale)
    }

    func scrollViewDidEndZooming(_ scrollView: UIScrollView, with view: UIView?, atScale scale: CGFloat) {
        onScaleChanged?(scale)
        settleToFitIfFitted()
        Task { @MainActor [weak self] in
            // Yield so the binding-write task scheduled inside `onScaleChanged`
            // runs before we reopen the gate, mirroring the macOS guard (#748).
            await Task.yield()
            self?.isUserMagnifying = false
        }
    }

    /// The scroll view laid out: apply a fit that was waiting for a size, or a re-fit after a resize (#6559, #4279).
    func layoutDidChange() {
        guard let scrollView else { return }
        let hasImage = (imageView as? UIImageView)?.image != nil
        if owner.applyAutomaticFit(scrollView: scrollView, coordinator: self, hasImage: hasImage) != nil {
            centerContent()
        }
    }

    func scrollViewDidScroll(_ scrollView: UIScrollView) {
        updateVisibleRect()
    }

    func centerContent() {
        guard let scrollView = scrollView,
              let image = (imageView as? UIImageView)?.image else { return }

        let imageSize = image.size
        let viewSize = scrollView.bounds.size
        let zoom = scrollView.zoomScale
        let scaledW = imageSize.width * zoom
        let scaledH = imageSize.height * zoom

        let insetX = max(0, (viewSize.width - scaledW) / 2)
        let insetY = max(0, (viewSize.height - scaledH) / 2)
        scrollView.contentInset = UIEdgeInsets(top: insetY, left: insetX, bottom: insetY, right: insetX)
        // Every zoom change passes through here, so this is where the fitted page stops scrolling (#6559).
        syncPanningToZoom()
    }

    func updateVisibleRect() {
        guard let scrollView = scrollView,
              let image = (imageView as? UIImageView)?.image else { return }

        let contentOffset = scrollView.contentOffset
        let visibleSize = scrollView.bounds.size
        let zoom = scrollView.zoomScale
        let imageSize = image.size
        let contentSize = CGSize(width: imageSize.width * zoom, height: imageSize.height * zoom)

        // Account for content insets used to center smaller images.
        let visibleOriginX = contentOffset.x + scrollView.contentInset.left
        let visibleOriginY = contentOffset.y + scrollView.contentInset.top

        let normalizedWidth = min(1.0, visibleSize.width / contentSize.width)
        let normalizedHeight = min(1.0, visibleSize.height / contentSize.height)
        let normalizedX = visibleOriginX / contentSize.width
        let normalizedY = 1.0 - (visibleOriginY + visibleSize.height) / contentSize.height

        let rect = CGRect(
            x: max(0, min(1 - normalizedWidth, normalizedX)),
            y: max(0, min(1 - normalizedHeight, normalizedY)),
            width: normalizedWidth,
            height: normalizedHeight
        )
        onVisibleRectChanged?(rect)
    }

    /// Scale that fits the image in the scroll view. The rule lives in
    /// `PreviewInitialZoomPolicy` so image and PDF previews open alike (#4279);
    /// `nil` means "not measurable yet".
    func calculateFitScale() -> CGFloat? {
        guard let scrollView = scrollView,
              let image = (imageView as? UIImageView)?.image,
              let fit = PreviewInitialZoomPolicy.fitScale(
                  contentSize: image.size,
                  paneSize: scrollView.bounds.size
              ) else { return nil }
        return PreviewInitialZoomPolicy.clamped(fit, kind: .raster)
    }

    // MARK: - Zoom Ownership (#4279)

    /// True once the user has taken manual control of the zoom (pinch or a
    /// toolbar zoom command). While false the preview keeps re-fitting to the
    /// pane on resize/rotation; once true the scale is frozen until a different
    /// item is displayed.
    var userHasZoomedManually = false

    /// Pane size the last automatic fit was computed for.
    private var lastAutoFitPaneSize: CGSize = .zero

    /// The user just took over the zoom — stop auto-fitting.
    func markManualZoom() {
        userHasZoomedManually = true
    }

    /// A new item is on screen — hand the zoom back to the automatic fit.
    func resetZoomOwnershipForNewItem() {
        userHasZoomedManually = false
        lastAutoFitPaneSize = .zero
    }

    /// Record that an automatic fit has just been applied at the pane's
    /// current size.
    func noteAutoFitApplied() {
        lastAutoFitPaneSize = scrollView?.bounds.size ?? .zero
    }

    /// The scale to re-fit to because the pane resized and the user hasn't
    /// taken over, or `nil` when nothing should change.
    func autoRefitScale() -> CGFloat? {
        guard !userHasZoomedManually, let scrollView = scrollView else { return nil }
        let paneSize = scrollView.bounds.size
        // Sub-point jitter is layout noise, not a resize.
        guard abs(paneSize.width - lastAutoFitPaneSize.width) > 0.5
                || abs(paneSize.height - lastAutoFitPaneSize.height) > 0.5,
              let fit = calculateFitScale() else { return nil }
        lastAutoFitPaneSize = paneSize
        return fit
    }

    /// Scroll to a normalized position (0-1 coordinates, top-left origin).
    func scrollToNormalizedPosition(_ normalizedOrigin: CGPoint) {
        guard let scrollView = scrollView,
              let image = (imageView as? UIImageView)?.image else { return }
        let imageSize = image.size
        let zoom = scrollView.zoomScale
        let visibleHeight = scrollView.bounds.height / zoom
        let docX = normalizedOrigin.x * imageSize.width * zoom - scrollView.contentInset.left
        let docY = (1.0 - normalizedOrigin.y) * imageSize.height * zoom - visibleHeight - scrollView.contentInset.top
        scrollView.setContentOffset(CGPoint(x: docX, y: docY), animated: false)
    }

    /// Pan the visible area by document points.
    func panBy(x deltaX: CGFloat, y deltaY: CGFloat) {
        guard let scrollView = scrollView,
              let image = (imageView as? UIImageView)?.image else { return }
        let zoom = scrollView.zoomScale
        let visibleRect = CGRect(
            origin: CGPoint(
                x: scrollView.contentOffset.x + scrollView.contentInset.left,
                y: scrollView.contentOffset.y + scrollView.contentInset.top
            ),
            size: scrollView.bounds.size
        )
        let maxX = max(0, image.size.width * zoom - visibleRect.width)
        let maxY = max(0, image.size.height * zoom - visibleRect.height)
        let targetX = min(max(0, visibleRect.origin.x + deltaX), maxX) - scrollView.contentInset.left
        let targetY = min(max(0, visibleRect.origin.y + deltaY), maxY) - scrollView.contentInset.top
        scrollView.setContentOffset(CGPoint(x: targetX, y: targetY), animated: false)
    }
}

// MARK: - Page swipe (#6559)

extension ImageWithCursorTrackingIOSCoordinator: UIGestureRecognizerDelegate {
    /// A fitted page does not scroll, so a sideways swipe on it turns the page instead of nudging the image; a
    /// zoomed-in page pans as before. The pinch is a separate recognizer, so zooming works either way. The pinch's
    /// floor, the fitted size, is kept here too.
    func syncPanningToZoom() {
        guard let scrollView else { return }
        let fit = calculateFitScale()
        scrollView.minimumZoomScale = PageSwipe.minimumZoom(fitScale: fit, minScale: owner.minScale)
        let zoomedIn = PageSwipe.isZoomedIn(scale: scrollView.zoomScale, fitScale: fit)
        if scrollView.isScrollEnabled != zoomedIn { scrollView.isScrollEnabled = zoomedIn }
        // A page that isn't zoomed in always rests centred: a new page, a fit, a pinch back out. Without this a page
        // kept the last one's scroll position and could sit off to the left or out of view. Not mid-pinch, where
        // the pinch owns the offset.
        guard !zoomedIn, !scrollView.isZooming, !scrollView.isZoomBouncing,
              let image = (imageView as? UIImageView)?.image else { return }
        let zoom = scrollView.zoomScale
        let resting = PageSwipe.restingOffset(
            scaledContent: CGSize(width: image.size.width * zoom, height: image.size.height * zoom),
            viewSize: scrollView.bounds.size
        )
        if abs(scrollView.contentOffset.x - resting.x) > 0.5 || abs(scrollView.contentOffset.y - resting.y) > 0.5 {
            scrollView.contentOffset = resting
        }
    }

    /// A pinch that ends at or near the fitted size springs back to exactly the whole page, centred, as in Photos
    /// (#6559). Scrolling is off there, so a page left off-centre would otherwise stay stuck where the pinch let go.
    func settleToFitIfFitted() {
        guard let scrollView, let fit = calculateFitScale(),
              !PageSwipe.isZoomedIn(scale: scrollView.zoomScale, fitScale: fit) else { return }
        // centerContent puts the offset at the resting point too (syncPanningToZoom).
        UIView.animate(withDuration: 0.25, delay: 0, options: [.curveEaseOut, .allowUserInteraction]) {
            scrollView.zoomScale = fit
            self.centerContent()
        }
        // Back at fit, the automatic fit owns the zoom again, so a resize re-fits (#4279).
        userHasZoomedManually = false
        noteAutoFitApplied()
        onScaleChanged?(fit)
    }

    /// The page-swipe recognizer, on the scroll view itself: a SwiftUI drag over the representable lost to the
    /// scroll view's own pan.
    func installPageSwipe(on scrollView: UIScrollView) {
        let pan = UIPanGestureRecognizer(target: self, action: #selector(handlePageSwipe(_:)))
        pan.delegate = self
        pan.maximumNumberOfTouches = 1
        scrollView.addGestureRecognizer(pan)
    }

    @objc func handlePageSwipe(_ pan: UIPanGestureRecognizer) {
        guard pan.state == .ended, let view = pan.view else { return }
        let translation = pan.translation(in: view)
        let size = CGSize(width: translation.x, height: translation.y)
        let step = PageSwipe.step(
            translation: size,
            predictedEnd: PageSwipe.predictedEnd(translation: size, velocity: pan.velocity(in: view)),
            isZoomedIn: false
        )
        if let step { owner.onPageStep?(step) }
    }

    func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        guard let pan = gestureRecognizer as? UIPanGestureRecognizer,
              pan !== scrollView?.panGestureRecognizer else { return true }
        guard owner.onPageStep != nil, let scrollView else { return false }
        let zoomedIn = PageSwipe.isZoomedIn(scale: scrollView.zoomScale, fitScale: calculateFitScale())
        return PageSwipe.claimsDrag(velocity: pan.velocity(in: pan.view), isZoomedIn: zoomedIn)
    }

    /// The pinch and the image's tap still see the touches.
    func gestureRecognizer(
        _ gestureRecognizer: UIGestureRecognizer,
        shouldRecognizeSimultaneouslyWith otherGestureRecognizer: UIGestureRecognizer
    ) -> Bool {
        true
    }
}

// Make Coordinator available as ImageWithCursorTracking.Coordinator for API compatibility
extension ImageWithCursorTracking {
    typealias Coordinator = ImageWithCursorTrackingIOSCoordinator
}
#endif
