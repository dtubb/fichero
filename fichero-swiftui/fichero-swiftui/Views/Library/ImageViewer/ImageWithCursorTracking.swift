import SwiftUI
import AppKit
import OSLog

// This file requires large bodies due to complex AppKit integration
/// NSViewRepresentable wrapper for an image view with cursor tracking and loupe functionality
struct ImageWithCursorTracking: NSViewRepresentable {
    private static let logger = Logger(subsystem: "com.tubb.Fichero", category: "ImageWithCursorTracking")

    let url: URL
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
        scrollView.backgroundColor = NSColor.windowBackgroundColor
        scrollView.scrollerStyle = .overlay
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

        if let image = NSImage(contentsOf: url) {
            imageView.image = image
            imageView.frame = NSRect(origin: .zero, size: image.size)
            Self.logger.info("makeNSView: Set image size=\(image.size.width)x\(image.size.height)")
            Task { @MainActor in
                self.imageSize = image.size
            }
        } else {
            Self.logger.error("makeNSView: Failed to load image from: \(url.lastPathComponent)")
        }

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

        // Initial center will happen in updateNSView after layout
        context.coordinator.needsInitialCenter = true

        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        // Fit-to-window and center on first layout when bounds are known
        if context.coordinator.needsInitialCenter && scrollView.bounds.width > 0 && scrollView.bounds.height > 0 {
            context.coordinator.needsInitialCenter = false
            // Default to fit-to-window scale unless a saved scale exists
            if let fitScale = context.coordinator.calculateFitScale() {
                let savedScale = scale
                // If scale is still the 1.0 default (no saved value), use fit scale
                if abs(savedScale - 1.0) < 0.01 {
                    scrollView.magnification = fitScale
                    Task { @MainActor in
                        self.scale = fitScale
                    }
                }
            }
            centerImage(scrollView: scrollView, imageView: context.coordinator.imageView!)
            // Reveal after centering (was hidden to prevent flash)
            if scrollView.alphaValue < 1 {
                scrollView.alphaValue = 1
            }
        }
        if abs(scrollView.magnification - scale) > 0.01 {
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

            if context.coordinator.currentURL != url {
                if let image = NSImage(contentsOf: url) {
                    imageView.image = image
                    imageView.frame = NSRect(origin: .zero, size: image.size)
                    imageView.loupePosition = nil  // Reset loupe on image change
                    context.coordinator.currentURL = url
                    Task { @MainActor in
                        self.imageSize = image.size
                    }
                    centerImage(scrollView: scrollView, imageView: imageView)
                }
            }
        }

        // Keep content centered when the viewport size changes.
        updateContentInsets(scrollView: scrollView, imageView: context.coordinator.imageView!)

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
        var onVisibleRectChanged: ((CGRect) -> Void)?
        var magnifyGesture: NSMagnificationGestureRecognizer?
        var doubleClickGesture: NSClickGestureRecognizer?
        var onZoomIn: (() -> Void)?
        var needsInitialCenter: Bool = false
        private var initialMagnification: CGFloat = 1.0

        @MainActor
        @objc func boundsDidChange(_ notification: Notification) {
            updateContentInsetsForCurrentLayout()
            updateVisibleRect()
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
            // Check if cursor is over loupe - if so, zoom the loupe instead of main image
            if let trackingView = imageView as? TrackingImageView,
               trackingView.loupeEnabled,
               let loupeViewPos = trackingView.loupeViewPosition {
                let location = gesture.location(in: trackingView)
                let loupeRadius = trackingView.loupeSize / 2
                let distance = hypot(location.x - loupeViewPos.x, location.y - loupeViewPos.y)
                if distance <= loupeRadius {
                    // Over loupe - zoom loupe magnification
                    switch gesture.state {
                    case .began:
                        initialMagnification = trackingView.loupeMagnification
                    case .changed:
                        let newMag = initialMagnification * (1 + gesture.magnification)
                        let clampedMag = max(1.5, min(10.0, newMag))
                        trackingView.loupeMagnification = clampedMag
                        trackingView.onLoupeMagnificationChanged?(clampedMag)
                        trackingView.needsDisplay = true
                    default:
                        break
                    }
                }
            }
            // If not over loupe, let NSScrollView's built-in magnification handle it
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
