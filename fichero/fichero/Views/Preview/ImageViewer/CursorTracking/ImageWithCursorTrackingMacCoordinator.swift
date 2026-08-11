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
    var onVisibleRectChanged: ((CGRect) -> Void)?
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
    private var initialMagnification: CGFloat = 1.0

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
        let viewSize = scrollView.bounds.size
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

    @MainActor
    @objc func handleMagnify(_ gesture: NSMagnificationGestureRecognizer) {
        // Check if cursor is over loupe — zoom the loupe instead of the main image.
        if let trackingView = imageView as? TrackingImageView,
           trackingView.loupeEnabled,
           let loupeViewPos = trackingView.loupeViewPosition {
            let location = gesture.location(in: trackingView)
            let loupeRadius = trackingView.loupeSize / 2
            let distance = hypot(location.x - loupeViewPos.x, location.y - loupeViewPos.y)
            if distance <= loupeRadius {
                switch gesture.state {
                case .began:
                    initialMagnification = trackingView.loupeMagnification
                case .changed:
                    let newMag = initialMagnification * (1 + gesture.magnification)
                    let clampedMag = max(0.25, min(20.0, newMag))
                    trackingView.loupeMagnification = clampedMag
                    trackingView.onLoupeMagnificationChanged?(clampedMag)
                    trackingView.needsDisplay = true
                default:
                    break
                }
                return
            }
        }

        // Not over loupe — forward the pinch to the scroll view.
        // NSScrollView's built-in magnification would normally do this, but
        // our custom recognizer captures the event first and without forwarding,
        // the scroll view never zooms (#562).
        guard let scrollView = scrollView else { return }
        switch gesture.state {
        case .began:
            isUserMagnifying = true
            // A pinch hands zoom control to the user (#4279).
            markManualZoom()
            initialMagnification = scrollView.magnification
        case .changed:
            let newMag = initialMagnification * (1 + gesture.magnification)
            let clamped = max(scrollView.minMagnification, min(scrollView.maxMagnification, newMag))
            // Set magnification centred on the gesture location so the pinch
            // feels anchored under the cursor.
            let location = gesture.location(in: scrollView.contentView)
            scrollView.setMagnification(clamped, centeredAt: location)
        case .ended, .cancelled, .failed:
            // #596: write the final magnification back to the @Binding
            // so the next updateNSView sync-check sees matching values
            // and doesn't snap the zoom back to the pre-pinch scale.
            //
            // #748: ORDER MATTERS. Setting `isUserMagnifying = false`
            // synchronously before `onScaleChanged` runs lets SwiftUI
            // fire `updateNSView` in the gap before the Task @MainActor
            // queued inside `onScaleChanged` writes the binding. That
            // updateNSView sees `scale` still at the pre-pinch value
            // and reverts magnification — the user sees a ~250ms flash
            // to the old zoom. Defer the gate-reopen until after the
            // binding write has had a chance to propagate.
            onScaleChanged?(scrollView.magnification)
            Task { @MainActor [weak self] in
                // Yield once so the binding-write task scheduled inside
                // `onScaleChanged` runs first (Swift Concurrency
                // preserves FIFO order on the main actor; yielding
                // makes that explicit and survives priority changes).
                await Task.yield()
                self?.isUserMagnifying = false
            }
        default:
            break
        }
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

        onVisibleRectChanged?(rect)
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
                  paneSize: scrollView.bounds.size
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
        lastAutoFitPaneSize = scrollView?.bounds.size ?? .zero
    }

    /// The scale to re-fit to because the pane resized and the user hasn't
    /// taken over, or `nil` when nothing should change.
    @MainActor
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

    /// Center the content in the scroll view using frame expansion + imageAlignment.
    @MainActor
    func centerContent() {
        guard let scrollView = scrollView,
              let imgView = imageView as? NSImageView,
              let image = imgView.image else { return }

        let imageSize = image.size
        let viewSize = scrollView.bounds.size
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
