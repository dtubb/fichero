#if canImport(AppKit)
import AppKit
import SwiftUI
import CoreImage
import ImageIO
import OSLog

/// Load an image decoded to SDR so iPhone HEIC HDR gain maps don't elevate
/// the window's EDR headroom and wash out surrounding UI. Setting
/// `preferredImageDynamicRange = .standard` on NSImageView alone isn't
/// sufficient — if the NSImage carries an HDR representation the system
/// still raises headroom. Decoding via ImageIO with
/// `kCGImageSourceDecodeRequest = kCGImageSourceDecodeToSDR` (macOS 14+)
/// strips the HDR payload at load time.
///
/// We also apply the EXIF `Orientation` tag manually — `NSImage(contentsOf:)`
/// does this automatically via its representation system, but the ImageIO
/// path returns raw pixels. Without the manual rotate, iPhone photos taken
/// in portrait or upside-down come in sideways.
private func loadSDRImage(from url: URL) -> NSImage? {
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else {
        return NSImage(contentsOf: url)
    }
    let options: [CFString: Any] = [
        kCGImageSourceDecodeRequest: kCGImageSourceDecodeToSDR,
        kCGImageSourceShouldCache: true
    ]
    guard let cgImage = CGImageSourceCreateImageAtIndex(source, 0, options as CFDictionary) else {
        return NSImage(contentsOf: url)
    }

    let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
    let orientationRaw = (props?[kCGImagePropertyOrientation] as? UInt32) ?? 1
    let orientation = CGImagePropertyOrientation(rawValue: orientationRaw) ?? .up
    let finalCGImage: CGImage = {
        guard orientation != .up else { return cgImage }
        let ci = CIImage(cgImage: cgImage).oriented(orientation)
        let ctx = CIContext(options: nil)
        return ctx.createCGImage(ci, from: ci.extent) ?? cgImage
    }()
    return NSImage(
        cgImage: finalCGImage,
        size: CGSize(width: finalCGImage.width, height: finalCGImage.height)
    )
}

// This file requires large bodies due to complex AppKit integration
/// NSViewRepresentable wrapper for an image view with cursor tracking and loupe functionality
struct ImageWithCursorTracking: NSViewRepresentable {
    private static let logger = Logger(subsystem: "app.fichero.fichero", category: "ImageWithCursorTracking")

    let url: URL?
    /// When non-nil, this image is used directly instead of loading from `url`.
    /// Enables editor mode where the canvas shows a backend-rendered preview (#1402).
    var overrideImage: PlatformImage? = nil
    @Binding var scale: CGFloat
    @Binding var cursorPosition: CGPoint  // Normalized 0-1 position in image
    @Binding var imageSize: CGSize
    @Binding var visibleRect: CGRect  // Normalized 0-1 visible area
    let minScale: CGFloat
    let maxScale: CGFloat
    let loupeEnabled: Bool
    let loupeLocked: Bool
    @Binding var loupeMagnification: CGFloat
    @Binding var loupeSize: CGFloat
    @Binding var coordinator: Coordinator?  // Exposed for external scroll control

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = true
        scrollView.allowsMagnification = true  // Use built-in Mac zoom behavior
        scrollView.minMagnification = minScale
        scrollView.maxMagnification = maxScale
        scrollView.magnification = scale
        scrollView.backgroundColor = NSColor(white: 0.88, alpha: 1)
        scrollView.scrollerStyle = .overlay  // Auto-hiding overlay scrollers like Preview.app
        scrollView.automaticallyAdjustsContentInsets = false
        scrollView.alphaValue = 0  // Hidden until first center to prevent flash
        scrollView.postsBoundsChangedNotifications = true
        scrollView.contentView.postsBoundsChangedNotifications = true

        // Add magnification gesture recognizer for loupe pinch-to-zoom
        // This works alongside NSScrollView's built-in magnification
        let magnifyGesture = NSMagnificationGestureRecognizer(
            target: context.coordinator,
            action: #selector(Coordinator.handleMagnify(_:))
        )
        magnifyGesture.delegate = context.coordinator
        scrollView.addGestureRecognizer(magnifyGesture)
        context.coordinator.magnifyGesture = magnifyGesture

        // Add double-click gesture for zoom
        let doubleClickGesture = NSClickGestureRecognizer(
            target: context.coordinator,
            action: #selector(Coordinator.handleDoubleClick(_:))
        )
        doubleClickGesture.numberOfClicksRequired = 2
        scrollView.addGestureRecognizer(doubleClickGesture)
        context.coordinator.doubleClickGesture = doubleClickGesture

        // Create tracking image view with loupe
        let imageView = TrackingImageView()
        imageView.imageScaling = .scaleNone  // We'll handle sizing
        // iPhone HEIC photos carry an HDR gain map. NSImageView defaults to
        // `.high` dynamic range on macOS 14+, which elevates the window's EDR
        // headroom and makes surrounding SDR UI look washed out. Lock to
        // `.standard` so photos render as tone-mapped SDR like Preview.app's
        // default behaviour.
        imageView.preferredImageDynamicRange = .standard
        imageView.onCursorMoved = { normalizedPos in
            Task { @MainActor in
                // Only update if position is within bounds (clamp to valid range)
                // This prevents edge artifacts when cursor leaves image area
                let clampedPos = CGPoint(
                    x: max(0, min(1, normalizedPos.x)),
                    y: max(0, min(1, normalizedPos.y))
                )
                self.cursorPosition = clampedPos
            }
        }
        imageView.onLoupeMagnificationChanged = { newMag in
            Task { @MainActor in
                self.loupeMagnification = newMag
            }
        }
        imageView.onLoupeSizeChanged = { newSize in
            Task { @MainActor in
                self.loupeSize = newSize
            }
        }
        imageView.loupeMagnification = loupeMagnification
        imageView.loupeSize = loupeSize

        let initialImage = overrideImage ?? url.flatMap(loadSDRImage)
        if let image = initialImage {
            imageView.image = image
            imageView.frame = NSRect(origin: .zero, size: image.size)
            Self.logger.info("makeNSView: Set image size=\(image.size.width)x\(image.size.height)")
            Task { @MainActor in
                self.imageSize = image.size
            }
        } else {
            Self.logger.error("makeNSView: Failed to load image")
        }
        context.coordinator.currentOverrideImage = overrideImage

        scrollView.documentView = imageView
        context.coordinator.scrollView = scrollView
        context.coordinator.imageView = imageView
        Self.logger.info(
            "makeNSView: Set documentView, bounds=\(scrollView.bounds.width)x\(scrollView.bounds.height)"
        )

        // Observe scroll/zoom changes for visible rect
        NotificationCenter.default.addObserver(
            context.coordinator,
            selector: #selector(Coordinator.boundsDidChange(_:)),
            name: NSView.boundsDidChangeNotification,
            object: scrollView.contentView
        )
        context.coordinator.onVisibleRectChanged = { rect in
            Task { @MainActor in
                self.visibleRect = rect
            }
        }
        // #596 (2nd attempt): fires once at gesture end with the final
        // magnification. Writes the @Binding so updateNSView's sync-check
        // matches and doesn't revert the zoom. Gate on epsilon to avoid
        // a self-triggering re-render loop on the initial fit cascade.
        context.coordinator.onScaleChanged = { newScale in
            Task { @MainActor in
                if abs(self.scale - newScale) > 0.01 {
                    self.scale = newScale
                }
            }
        }

        // Initial center will happen in updateNSView after layout
        context.coordinator.needsInitialCenter = true

        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        // Fit-to-window and center on first layout when bounds are known
        if context.coordinator.needsInitialCenter && scrollView.bounds.width > 0 && scrollView.bounds.height > 0 {
            context.coordinator.needsInitialCenter = false
            // Fit to window on first layout (like Preview.app)
            if let fitScale = context.coordinator.calculateFitScale() {
                scrollView.magnification = fitScale
                Task { @MainActor in
                    self.scale = fitScale
                }
            }
            centerImage(scrollView: scrollView, imageView: context.coordinator.imageView!)
            // Reveal after centering (was hidden to prevent flash)
            if scrollView.alphaValue < 1 {
                scrollView.alphaValue = 1
            }
        }
        // #596: skip the magnification→scale sync while a pinch is active.
        // NSMagnificationGestureRecognizer mutates scrollView.magnification
        // directly; writing `scale` back on every frame would race with
        // that write and effectively pin the zoom to the pre-pinch value.
        // The binding gets its write-back at gesture `.ended` via
        // `Coordinator.onScaleChanged` instead.
        if !context.coordinator.isUserMagnifying,
           abs(scrollView.magnification - scale) > 0.01 {
            scrollView.magnification = scale
        }

        if let imageView = context.coordinator.imageView as? TrackingImageView {
            // Update loupe enabled state
            imageView.loupeEnabled = loupeEnabled

            // Auto-show loupe at center when enabled and no position exists
            // Use slight delay to let view settle before drawing
            if loupeEnabled && imageView.loupePosition == nil {
                Task { @MainActor [weak imageView] in
                    try? await Task.sleep(for: .milliseconds(50))
                    guard let imageView = imageView,
                          imageView.loupeEnabled,
                          imageView.loupePosition == nil else { return }
                    imageView.showLoupeAtCenter()
                }
            }

            imageView.loupeLocked = loupeLocked
            imageView.loupeMagnification = loupeMagnification
            imageView.loupeSize = loupeSize

            // Detect image change: either a new overrideImage or a new URL.
            let overrideChanged = overrideImage !== context.coordinator.currentOverrideImage
            let urlChanged = context.coordinator.currentURL != url
            let needsImageUpdate = overrideImage != nil ? overrideChanged : urlChanged

            if needsImageUpdate {
                let newImage = overrideImage ?? url.flatMap(loadSDRImage)
                if let image = newImage {
                    imageView.image = image
                    imageView.frame = NSRect(origin: .zero, size: image.size)
                    imageView.loupePosition = nil  // Reset loupe on image change
                    context.coordinator.currentURL = url
                    context.coordinator.currentOverrideImage = overrideImage
                    Task { @MainActor in
                        self.imageSize = image.size
                    }
                    // Apply the right zoom IN THE SAME FRAME as the new image
                    // is set. Otherwise the new image renders at the previous
                    // image's magnification for one frame, then snaps —
                    // visible flash. The current `scale` binding holds either
                    // the previous image's saved scale (if user customized it)
                    // or the previous fit. Always recalculate fit for the new
                    // image here; the parent will overwrite via `scale`
                    // binding on next updateNSView if a saved scale exists for
                    // this image. (#773 + #777)
                    if let fitScale = context.coordinator.calculateFitScale() {
                        scrollView.magnification = fitScale
                        Task { @MainActor in
                            self.scale = fitScale
                        }
                    }
                    centerImage(scrollView: scrollView, imageView: imageView)
                    if scrollView.alphaValue < 1 { scrollView.alphaValue = 1 }
                }
            }
        }

        // Keep content centered when the viewport size changes.
        updateContentInsets(scrollView: scrollView, imageView: context.coordinator.imageView!)

        // Some first-paint paths reach here with a loaded image and real bounds
        // but without the reveal callback having fired yet. Reveal eagerly so
        // the image doesn't stay blank until the next interaction.
        if scrollView.alphaValue < 1,
           scrollView.bounds.width > 0,
           scrollView.bounds.height > 0,
           let imageView = context.coordinator.imageView as? NSImageView,
           imageView.image != nil {
            scrollView.alphaValue = 1
        }

        // Update visible rect
        context.coordinator.updateVisibleRect()
    }

    func makeCoordinator() -> Coordinator {
        let coord = Coordinator()
        Task { @MainActor in
            self.coordinator = coord
        }
        return coord
    }

    /// Center the image by expanding the image view frame when the scaled image
    /// is smaller than the viewport, using imageAlignment for native centering.
    private func centerImage(scrollView: NSScrollView, imageView: NSView) {
        guard let imgView = imageView as? NSImageView, let image = imgView.image else {
            Self.logger.warning("centerImage: No image or imageView")
            return
        }

        layoutImageView(imgView, image: image, in: scrollView)
    }

    /// Keep the image view frame in sync with the viewport on resize/zoom.
    private func updateContentInsets(scrollView: NSScrollView, imageView: NSView) {
        guard let imgView = imageView as? NSImageView, let image = imgView.image else { return }

        layoutImageView(imgView, image: image, in: scrollView)
    }

    /// Shared layout: when the scaled image is smaller than the viewport,
    /// expand the image view frame so AppKit's imageAlignment centers it.
    private func layoutImageView(_ imgView: NSImageView, image: NSImage, in scrollView: NSScrollView) {
        let imageSize = image.size
        let viewSize = scrollView.bounds.size
        let mag = scrollView.magnification
        let scaledW = imageSize.width * mag
        let scaledH = imageSize.height * mag

        // Determine needed frame size (at least viewport/mag, at least image size)
        let frameW = max(imageSize.width, viewSize.width / mag)
        let frameH = max(imageSize.height, viewSize.height / mag)

        let needsExpand = scaledW < viewSize.width || scaledH < viewSize.height
        let targetFrame = NSRect(origin: .zero, size: CGSize(width: frameW, height: frameH))

        if imgView.frame != targetFrame {
            imgView.frame = targetFrame
        }
        imgView.imageAlignment = needsExpand ? .alignCenter : .alignTopLeft

        // Clear any stale contentInsets from previous approach
        scrollView.contentInsets = NSEdgeInsets()
    }

    class Coordinator: NSObject, NSGestureRecognizerDelegate {
        var scrollView: NSScrollView?
        var imageView: NSView?
        var currentURL: URL?
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

        /// Calculate the scale needed to fit the image in the scroll view
        @MainActor
        func calculateFitScale() -> CGFloat? {
            guard let scrollView = scrollView,
                  let imageView = imageView as? NSImageView,
                  let image = imageView.image else { return nil }

            let viewSize = scrollView.bounds.size
            guard viewSize.width > 0, viewSize.height > 0 else { return nil }

            let imageSize = image.size
            let scaleX = viewSize.width / imageSize.width
            let scaleY = viewSize.height / imageSize.height

            // Fit scale is the minimum of x/y scales, capped at 1.0 (don't upscale)
            return min(scaleX, scaleY, 1.0)
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
}
#elseif canImport(UIKit)
import UIKit
import SwiftUI
import CoreImage
import ImageIO
import OSLog

private func loadSDRImage(from url: URL) -> PlatformImage? {
    // iOS: load normally. Orientation metadata is handled by UIImage.
    return PlatformImage(contentsOfFile: url.path)
}

/// UIViewRepresentable wrapper for an image view with basic zoom/pan on iOS.
/// Loupe drawing is stubbed through `TrackingImageView` to keep the same API
/// surface as macOS; the loupe is not yet rendered on iOS.
struct ImageWithCursorTracking: UIViewRepresentable {
    private static let logger = Logger(subsystem: "app.fichero.fichero", category: "ImageWithCursorTracking")

    let url: URL?
    var overrideImage: PlatformImage? = nil
    @Binding var scale: CGFloat
    @Binding var cursorPosition: CGPoint
    @Binding var imageSize: CGSize
    @Binding var visibleRect: CGRect
    let minScale: CGFloat
    let maxScale: CGFloat
    let loupeEnabled: Bool
    let loupeLocked: Bool
    @Binding var loupeMagnification: CGFloat
    @Binding var loupeSize: CGFloat
    @Binding var coordinator: Coordinator?

    func makeUIView(context: Context) -> UIScrollView {
        let scrollView = UIScrollView()
        scrollView.backgroundColor = UIColor(white: 0.88, alpha: 1)
        scrollView.delegate = context.coordinator
        scrollView.minimumZoomScale = minScale
        scrollView.maximumZoomScale = maxScale
        scrollView.zoomScale = scale
        scrollView.showsHorizontalScrollIndicator = true
        scrollView.showsVerticalScrollIndicator = true
        scrollView.alpha = 0

        let imageView = TrackingImageView()
        imageView.contentMode = .topLeft
        imageView.isUserInteractionEnabled = true

        imageView.onCursorMoved = { normalizedPos in
            Task { @MainActor in
                let clampedPos = CGPoint(
                    x: max(0, min(1, normalizedPos.x)),
                    y: max(0, min(1, normalizedPos.y))
                )
                self.cursorPosition = clampedPos
            }
        }
        imageView.onLoupeMagnificationChanged = { newMag in
            Task { @MainActor in
                self.loupeMagnification = newMag
            }
        }
        imageView.onLoupeSizeChanged = { newSize in
            Task { @MainActor in
                self.loupeSize = newSize
            }
        }
        imageView.loupeMagnification = loupeMagnification
        imageView.loupeSize = loupeSize

        let initialImage = overrideImage ?? url.flatMap(loadSDRImage)
        if let image = initialImage {
            imageView.image = image
            imageView.frame = CGRect(origin: .zero, size: image.size)
            scrollView.contentSize = image.size
            Self.logger.info("makeUIView: Set image size=\(image.size.width)x\(image.size.height)")
            Task { @MainActor in
                self.imageSize = image.size
            }
        } else {
            Self.logger.error("makeUIView: Failed to load image")
        }
        context.coordinator.currentOverrideImage = overrideImage

        scrollView.addSubview(imageView)
        context.coordinator.scrollView = scrollView
        context.coordinator.imageView = imageView

        context.coordinator.onVisibleRectChanged = { rect in
            Task { @MainActor in
                self.visibleRect = rect
            }
        }
        context.coordinator.onScaleChanged = { newScale in
            Task { @MainActor in
                if abs(self.scale - newScale) > 0.01 {
                    self.scale = newScale
                }
            }
        }
        context.coordinator.needsInitialCenter = true

        return scrollView
    }

    func updateUIView(_ scrollView: UIScrollView, context: Context) {
        context.coordinator.owner = self

        if context.coordinator.needsInitialCenter,
           scrollView.bounds.width > 0,
           scrollView.bounds.height > 0 {
            context.coordinator.needsInitialCenter = false
            if let fitScale = context.coordinator.calculateFitScale() {
                scrollView.zoomScale = fitScale
                Task { @MainActor in
                    self.scale = fitScale
                }
            }
            context.coordinator.centerContent()
            if scrollView.alpha < 1 {
                scrollView.alpha = 1
            }
        }

        if !context.coordinator.isUserMagnifying,
           abs(scrollView.zoomScale - scale) > 0.01 {
            scrollView.zoomScale = scale
        }

        if let imageView = context.coordinator.imageView as? TrackingImageView {
            imageView.loupeEnabled = loupeEnabled

            if loupeEnabled && imageView.loupePosition == nil {
                Task { @MainActor [weak imageView] in
                    try? await Task.sleep(for: .milliseconds(50))
                    guard let imageView = imageView,
                          imageView.loupeEnabled,
                          imageView.loupePosition == nil else { return }
                    imageView.showLoupeAtCenter()
                }
            }

            imageView.loupeLocked = loupeLocked
            imageView.loupeMagnification = loupeMagnification
            imageView.loupeSize = loupeSize

            let overrideChanged = overrideImage !== context.coordinator.currentOverrideImage
            let urlChanged = context.coordinator.currentURL != url
            let needsImageUpdate = overrideImage != nil ? overrideChanged : urlChanged

            if needsImageUpdate {
                let newImage = overrideImage ?? url.flatMap(loadSDRImage)
                if let image = newImage {
                    imageView.image = image
                    imageView.frame = CGRect(origin: .zero, size: image.size)
                    scrollView.contentSize = image.size
                    imageView.loupePosition = nil
                    context.coordinator.currentURL = url
                    context.coordinator.currentOverrideImage = overrideImage
                    Task { @MainActor in
                        self.imageSize = image.size
                    }
                    if let fitScale = context.coordinator.calculateFitScale() {
                        scrollView.zoomScale = fitScale
                        Task { @MainActor in
                            self.scale = fitScale
                        }
                    }
                    context.coordinator.centerContent()
                    if scrollView.alpha < 1 { scrollView.alpha = 1 }
                }
            }
        }

        context.coordinator.centerContent()
        context.coordinator.updateVisibleRect()

        if scrollView.alpha < 1,
           scrollView.bounds.width > 0,
           scrollView.bounds.height > 0,
           let imageView = context.coordinator.imageView as? UIImageView,
           imageView.image != nil {
            scrollView.alpha = 1
        }
    }

    func makeCoordinator() -> Coordinator {
        let coord = Coordinator(owner: self)
        Task { @MainActor in
            self.coordinator = coord
        }
        return coord
    }

    @MainActor
    final class Coordinator: NSObject, UIScrollViewDelegate {
        var owner: ImageWithCursorTracking
        weak var scrollView: UIScrollView?
        weak var imageView: UIView?
        var currentURL: URL?
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
        }

        func scrollViewDidZoom(_ scrollView: UIScrollView) {
            centerContent()
            updateVisibleRect()
            onScaleChanged?(scrollView.zoomScale)
        }

        func scrollViewDidEndZooming(_ scrollView: UIScrollView, with view: UIView?, atScale scale: CGFloat) {
            onScaleChanged?(scale)
            Task { @MainActor [weak self] in
                // Yield so the binding-write task scheduled inside `onScaleChanged`
                // runs before we reopen the gate, mirroring the macOS guard (#748).
                await Task.yield()
                self?.isUserMagnifying = false
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

            let x = max(0, (viewSize.width - scaledW) / 2)
            let y = max(0, (viewSize.height - scaledH) / 2)
            scrollView.contentInset = UIEdgeInsets(top: y, left: x, bottom: y, right: x)
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

        func calculateFitScale() -> CGFloat? {
            guard let scrollView = scrollView,
                  let image = (imageView as? UIImageView)?.image else { return nil }
            let viewSize = scrollView.bounds.size
            guard viewSize.width > 0, viewSize.height > 0 else { return nil }
            let imageSize = image.size
            let scaleX = viewSize.width / imageSize.width
            let scaleY = viewSize.height / imageSize.height
            return min(scaleX, scaleY, 1.0)
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
}

#endif
