#if canImport(AppKit)
import AppKit
import CoreImage
import ImageIO
import OSLog
import SwiftUI

/// NSViewRepresentable wrapper for an image view with cursor tracking and loupe functionality
struct ImageWithCursorTracking: NSViewRepresentable {
    static let logger = Logger(subsystem: "app.fichero.fichero", category: "ImageWithCursorTracking")

    let url: URL?
    /// When non-nil, this image is used directly instead of loading from `url`.
    /// Enables editor mode where the canvas shows a backend-rendered preview (#1402).
    var overrideImage: PlatformImage?
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

        scrollView.documentView = imageView
        context.coordinator.scrollView = scrollView
        context.coordinator.imageView = imageView

        // An override image is already decoded in memory — apply it synchronously.
        // A URL is decoded OFF the main thread (#3864); the placeholder (hidden
        // scroll view) shows until the ready image arrives, fit in the same turn.
        context.coordinator.currentOverrideImage = overrideImage
        if let overrideImage {
            imageView.image = overrideImage
            imageView.frame = NSRect(origin: .zero, size: overrideImage.size)
            Self.logger.info("makeNSView: Set image size=\(overrideImage.size.width)x\(overrideImage.size.height)")
            Task { @MainActor in
                self.imageSize = overrideImage.size
            }
        } else if let url {
            loadImageAsync(url: url, into: imageView, scrollView: scrollView, coordinator: context.coordinator)
        }
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
        // Fit-to-window and center on first layout when bounds are known AND the
        // image has actually decoded (#3864 — the decode is now async, so an early
        // updateNSView can run before the image exists; don't reveal an empty frame).
        let hasImage = (context.coordinator.imageView as? NSImageView)?.image != nil
        if context.coordinator.needsInitialCenter && hasImage
            && scrollView.bounds.width > 0 && scrollView.bounds.height > 0 {
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
                if let overrideImage {
                    // Already-decoded override: apply synchronously, fit in the same
                    // frame so the new image never renders at the old magnification
                    // for a frame (#773/#777).
                    imageView.image = overrideImage
                    imageView.frame = NSRect(origin: .zero, size: overrideImage.size)
                    imageView.loupePosition = nil  // Reset loupe on image change
                    context.coordinator.currentURL = url
                    context.coordinator.currentOverrideImage = overrideImage
                    Task { @MainActor in
                        self.imageSize = overrideImage.size
                    }
                    if let fitScale = context.coordinator.calculateFitScale() {
                        scrollView.magnification = fitScale
                        Task { @MainActor in
                            self.scale = fitScale
                        }
                    }
                    centerImage(scrollView: scrollView, imageView: imageView)
                    if scrollView.alphaValue < 1 { scrollView.alphaValue = 1 }
                } else if let url {
                    // Decode the new page OFF the main thread (#3864). The previous
                    // page stays visible until the ready image swaps in fitted, in one
                    // turn — no main-thread block, no wrong-magnification flash.
                    loadImageAsync(url: url, into: imageView, scrollView: scrollView, coordinator: context.coordinator)
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

    /// Decode `url` OFF the main thread, then apply the ready image on the main actor
    /// (#3864). Marks the URL requested immediately so re-renders during the decode
    /// don't re-kick it, and takes a token so a superseded page-flip's late decode is
    /// dropped. Fits in the same turn as the image when bounds are known; otherwise
    /// defers to `updateNSView`'s (image-gated) initial fit.
    func loadImageAsync(
        url: URL,
        into imageView: TrackingImageView,
        scrollView: NSScrollView,
        coordinator: Coordinator
    ) {
        coordinator.currentURL = url
        coordinator.currentOverrideImage = nil
        let token = coordinator.beginImageLoad()
        Task { @MainActor in
            guard let cgImage = await decodeSDRCGImage(from: url),
                  coordinator.isCurrentImageLoad(token) else { return }
            let image = NSImage(cgImage: cgImage, size: CGSize(width: cgImage.width, height: cgImage.height))
            imageView.image = image
            imageView.frame = NSRect(origin: .zero, size: image.size)
            imageView.loupePosition = nil
            self.imageSize = image.size
            if let fitScale = coordinator.calculateFitScale() {
                scrollView.magnification = fitScale
                self.scale = fitScale
                centerImage(scrollView: scrollView, imageView: imageView)
                if scrollView.alphaValue < 1 { scrollView.alphaValue = 1 }
            } else {
                coordinator.needsInitialCenter = true
            }
        }
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

}
#endif
