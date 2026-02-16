import SwiftUI
import AppKit
import OSLog

// MARK: - Zoomable Image Preview (with controls and magnifier)

struct ZoomableImagePreview: View {
    let url: URL

    private static let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ZoomableImagePreview")

    // These settings persist across image changes using AppStorage
    @AppStorage("imagePreview.magnifierEnabled") private var magnifierEnabled = false
    @AppStorage("imagePreview.loupeEnabled") private var loupeEnabled = false
    @AppStorage("imagePreview.loupeMagnification") private var loupeMagnification: Double = 3.0
    @AppStorage("imagePreview.loupeSize") private var loupeSize: Double = 150.0
    @AppStorage("imagePreview.panelMagnification") private var panelMagnification: Double = 4.0
    @AppStorage("imagePreview.panelHeight") private var panelHeight: Double = 120.0
    @AppStorage("imagePreview.magnifierLocked") private var magnifierLocked = false
    @AppStorage("imagePreview.loupeLocked") private var loupeLocked = false

    @State private var scale: CGFloat = 1.0
    @State private var minScale: CGFloat = 0.1
    @State private var maxScale: CGFloat = 10.0
    @State private var cursorPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)  // Current cursor position over image
    @State private var lockedPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)  // Position when locked
    @State private var imageSize: CGSize = .zero
    @State private var image: NSImage?
    @State private var visibleRect: CGRect = .zero  // Normalized 0-1
    @State private var imageCoordinator: ImageWithCursorTracking.Coordinator?

    /// The position to use for magnifier (locked or cursor)
    private var magnifierPosition: CGPoint {
        magnifierLocked ? lockedPosition : cursorPosition
    }

    var body: some View {
        VStack(spacing: 0) {
            // Zoom toolbar
            HStack(spacing: 12) {
                Button(action: zoomOut) {
                    Image(systemName: "minus.magnifyingglass")
                }
                .buttonStyle(.plain)
                .help("Zoom Out")

                Text("\(Int(scale * 100))%")
                    .font(.caption)
                    .monospacedDigit()
                    .frame(width: 50)

                Button(action: zoomIn) {
                    Image(systemName: "plus.magnifyingglass")
                }
                .buttonStyle(.plain)
                .help("Zoom In")

                Divider()
                    .frame(height: 16)

                Button(action: fitToWindow) {
                    Image(systemName: "arrow.up.left.and.arrow.down.right")
                }
                .buttonStyle(.plain)
                .help("Fit to Window")

                Button(action: actualSize) {
                    Image(systemName: "1.square")
                }
                .buttonStyle(.plain)
                .help("Actual Size (100%)")

                Divider()
                    .frame(height: 16)

                // Magnifier panel toggle
                Button {
                    magnifierEnabled.toggle()
                } label: {
                    Image(systemName: "rectangle.bottomhalf.inset.filled")
                }
                .buttonStyle(.plain)
                .foregroundColor(magnifierEnabled ? .accentColor : .primary)
                .help("Magnifier Panel")

                // Loupe toggle with zoom controls
                HStack(spacing: 4) {
                    Button {
                        loupeEnabled.toggle()
                    } label: {
                        Image(systemName: loupeEnabled ? "magnifyingglass.circle.fill" : "magnifyingglass.circle")
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(loupeEnabled ? .accentColor : .primary)
                    .help("Loupe (crosshairs follow cursor, Option+move to reposition, lock to freeze)")

                    if loupeEnabled {
                        Button {
                            loupeLocked.toggle()
                        } label: {
                            Image(systemName: loupeLocked ? "lock.fill" : "lock.open")
                        }
                        .buttonStyle(.plain)
                        .foregroundColor(loupeLocked ? .accentColor : .secondary)
                        .help(loupeLocked ? "Unlock loupe (crosshairs follow cursor)" : "Lock loupe (freeze view)")

                        Text(String(format: "%.1fx", CGFloat(loupeMagnification)))
                            .font(.caption2)
                            .monospacedDigit()
                            .foregroundColor(.secondary)
                            .frame(width: 32)

                        Text("\(Int(loupeSize))px")
                            .font(.caption2)
                            .monospacedDigit()
                            .foregroundColor(.secondary.opacity(0.7))
                    }
                }

                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(Color(.windowBackgroundColor))

            Divider()

            // Main content area
            ZStack(alignment: .topTrailing) {
                VStack(spacing: 0) {
                    // Image view with cursor tracking and integrated loupe
                    ImageWithCursorTracking(
                        url: url,
                        scale: $scale,
                        cursorPosition: $cursorPosition,
                        imageSize: $imageSize,
                        visibleRect: $visibleRect,
                        minScale: minScale,
                        maxScale: maxScale,
                        loupeEnabled: loupeEnabled,
                        loupeLocked: loupeLocked,
                        loupeMagnification: Binding(
                            get: { CGFloat(loupeMagnification) },
                            set: { loupeMagnification = Double($0) }
                        ),
                        loupeSize: Binding(
                            get: { CGFloat(loupeSize) },
                            set: { loupeSize = Double($0) }
                        ),
                        coordinator: $imageCoordinator
                    )

                    // Bottom magnifier panel
                    if magnifierEnabled, let img = image {
                        Divider()
                        MagnifierPanelView(
                            image: img,
                            cursorPosition: magnifierPosition,
                            imageSize: imageSize,
                            magnification: Binding(
                                get: { CGFloat(panelMagnification) },
                                set: { panelMagnification = Double($0) }
                            ),
                            panelHeight: Binding(
                                get: { CGFloat(panelHeight) },
                                set: { panelHeight = Double($0) }
                            ),
                            isLocked: $magnifierLocked,
                            onLockToggle: {
                                if !magnifierLocked {
                                    // Locking - save the current magnifier position
                                    lockedPosition = cursorPosition
                                }
                                magnifierLocked.toggle()
                            }
                        )
                        .frame(height: CGFloat(panelHeight))
                    }
                }

                // Mini-map navigator (top right) - show when zoomed in (visible rect < full) or loupe active
                if let img = image, visibleRect.width < 0.99 || visibleRect.height < 0.99 || loupeEnabled {
                    NavigatorMiniMap(
                        image: img,
                        visibleRect: visibleRect,
                        onRectangleDragged: { normalizedOrigin in
                            imageCoordinator?.scrollToNormalizedPosition(normalizedOrigin)
                        }
                    )
                    .frame(width: 150, height: 100)
                    .padding(8)
                }
            }
        }
        .onAppear {
            Self.logger.info("ZoomableImagePreview onAppear: loading \(url.lastPathComponent)")
            image = NSImage(contentsOf: url)
            if let img = image {
                imageSize = img.size
                Self.logger.info("Successfully loaded image: size=\(img.size.width)x\(img.size.height)")
            } else {
                Self.logger.error("Failed to load NSImage from: \(url.path)")
            }
        }
        .onChange(of: url) { _, newURL in
            Self.logger.info("ZoomableImagePreview URL changed: loading \(newURL.lastPathComponent)")
            image = NSImage(contentsOf: newURL)
            if let img = image {
                imageSize = img.size
                Self.logger.info("Successfully loaded new image: size=\(img.size.width)x\(img.size.height)")
            } else {
                Self.logger.error("Failed to load NSImage from: \(newURL.path)")
            }
        }
        .onKeyPress(.init("+"), phases: .down) { _ in
            zoomIn()
            return .handled
        }
        .onKeyPress(.init("="), phases: .down) { _ in
            // Also handle = key (same as + without shift)
            zoomIn()
            return .handled
        }
        .onKeyPress(.init("-"), phases: .down) { _ in
            zoomOut()
            return .handled
        }
        .onKeyPress(.init("0"), phases: .down) { _ in
            actualSize()
            return .handled
        }
        .onChange(of: magnifierLocked) { wasLocked, isLocked in
            if isLocked && !wasLocked {
                // Locking via menu command - save current position
                lockedPosition = cursorPosition
            }
        }
        .onKeyPress(.init("9"), phases: .down) { _ in
            fitToWindow()
            return .handled
        }
        .focusedSceneValue(\.imageZoomActions, ImageZoomActions(
            zoomIn: zoomIn,
            zoomOut: zoomOut,
            actualSize: actualSize,
            zoomToFit: fitToWindow,
            canZoomIn: scale < maxScale,
            canZoomOut: scale > minScale,
            currentScale: scale
        ))
    }

    // MARK: - Zoom Actions

    private func zoomIn() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = min(scale * 1.25, maxScale)
        }
    }

    private func zoomOut() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = max(scale / 1.25, minScale)
        }
    }

    private func fitToWindow() {
        // Calculate fit scale from coordinator if available
        if let fitScale = imageCoordinator?.calculateFitScale() {
            withAnimation(.easeInOut(duration: 0.2)) {
                scale = fitScale
            }
            // Center the content after a brief delay to let the scale apply
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(0.25))
                imageCoordinator?.centerContent()
            }
        }
    }

    private func actualSize() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = 1.0
        }
    }
}

// MARK: - Image with Cursor Tracking and Loupe

struct ImageWithCursorTracking: NSViewRepresentable {
    private static let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ImageWithCursorTracking")

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
        scrollView.backgroundColor = NSColor(white: 0.4, alpha: 1.0)  // Medium-dark gray like Preview.app
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
        // Center image on first layout when bounds are known
        if context.coordinator.needsInitialCenter && scrollView.bounds.width > 0 && scrollView.bounds.height > 0 {
            context.coordinator.needsInitialCenter = false
            centerImage(scrollView: scrollView, imageView: context.coordinator.imageView!)
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

    private func centerImage(scrollView: NSScrollView, imageView: NSView) {
        guard let imgView = imageView as? NSImageView, let image = imgView.image else {
            Self.logger.warning("centerImage: No image or imageView")
            return
        }

        let viewSize = scrollView.bounds.size
        let imageSize = image.size

        let scaleX = viewSize.width / imageSize.width
        let scaleY = viewSize.height / imageSize.height
        let fitScale = min(scaleX, scaleY, 1.0)

        Self.logger.info("centerImage: view=\(viewSize.width)x\(viewSize.height) img=\(imageSize.width)x\(imageSize.height)")
        scrollView.magnification = fitScale
        updateContentInsets(scrollView: scrollView, imageView: imageView)
    }

    /// Update content insets to center the image when it's smaller than the scroll view
    private func updateContentInsets(scrollView: NSScrollView, imageView: NSView) {
        guard let imgView = imageView as? NSImageView, let image = imgView.image else { return }

        let viewSize = scrollView.bounds.size
        let scaledImageSize = CGSize(
            width: image.size.width * scrollView.magnification,
            height: image.size.height * scrollView.magnification
        )

        // Calculate insets to center the image
        let horizontalInset = max(0, (viewSize.width - scaledImageSize.width) / 2)
        let verticalInset = max(0, (viewSize.height - scaledImageSize.height) / 2)

        scrollView.contentInsets = NSEdgeInsets(
            top: verticalInset,
            left: horizontalInset,
            bottom: verticalInset,
            right: horizontalInset
        )
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
            updateVisibleRect()
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

        /// Center the content in the scroll view
        @MainActor
        func centerContent() {
            guard let scrollView = scrollView,
                  let imageView = imageView as? NSImageView,
                  let image = imageView.image else { return }

            let imageSize = image.size
            let magnification = scrollView.magnification
            let scaledWidth = imageSize.width * magnification
            let scaledHeight = imageSize.height * magnification
            let viewSize = scrollView.bounds.size

            // Calculate centered position
            let centerX = max(0, (scaledWidth - viewSize.width) / 2)
            let centerY = max(0, (scaledHeight - viewSize.height) / 2)

            scrollView.contentView.scroll(to: CGPoint(x: centerX, y: centerY))
            scrollView.reflectScrolledClipView(scrollView.contentView)
        }
    }
}

// swiftlint:disable file_length
// This file contains complex AppKit integration code that cannot be easily split further

// MARK: - Tracking Image View with Loupe

class TrackingImageView: NSImageView {
    var onCursorMoved: ((CGPoint) -> Void)?
    var onLoupeMagnificationChanged: ((CGFloat) -> Void)?
    var onLoupeSizeChanged: ((CGFloat) -> Void)?
    var loupeEnabled: Bool = false {
        didSet {
            // Just redraw - user must click to place loupe
            needsDisplay = true
        }
    }
    var loupeLocked: Bool = false  // When locked, loupe doesn't follow mouse
    var loupePosition: CGPoint?  // Position in image coordinates (what we're looking at)
    var loupeViewPosition: CGPoint?  // Where loupe is displayed
    private var isDraggingLoupe = false
    private var isResizingLoupe = false
    private var dragOffset: CGSize = .zero
    private var resizeStartSize: CGFloat = 0
    private var resizeStartDistance: CGFloat = 0
    private let edgeThreshold: CGFloat = 12  // How close to edge to trigger resize
    var loupeSize: CGFloat = 150 {
        didSet {
            if loupePosition != nil {
                needsDisplay = true
            }
        }
    }
    private let minLoupeSize: CGFloat = 80
    private let maxLoupeSize: CGFloat = 400
    var loupeMagnification: CGFloat = 3.0 {
        didSet {
            if loupePosition != nil {
                needsDisplay = true
            }
        }
    }
    private let minLoupeMagnification: CGFloat = 1.5
    private let maxLoupeMagnification: CGFloat = 10.0

    /// Show loupe at center of visible area
    func showLoupeAtCenter() {
        guard let scrollView = enclosingScrollView else {
            // Fallback to view center
            let centerX = bounds.width / 2
            let centerY = bounds.height / 2
            loupePosition = CGPoint(x: centerX, y: centerY)
            loupeViewPosition = CGPoint(x: centerX, y: centerY)
            needsDisplay = true
            return
        }

        // Get visible rect center
        let visibleRect = scrollView.contentView.documentVisibleRect
        let centerX = visibleRect.midX
        let centerY = visibleRect.midY

        loupePosition = CGPoint(x: centerX, y: centerY)
        loupeViewPosition = CGPoint(x: centerX, y: centerY)
        needsDisplay = true
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        trackingAreas.forEach { removeTrackingArea($0) }
        addTrackingArea(NSTrackingArea(
            rect: bounds,
            options: [.activeInKeyWindow, .mouseMoved, .mouseEnteredAndExited],
            owner: self,
            userInfo: nil
        ))
    }

    override func mouseMoved(with event: NSEvent) {
        let location = convert(event.locationInWindow, from: nil)
        guard bounds.width > 0, bounds.height > 0 else { return }

        // Option + move: reposition crosshairs (what loupe is looking at)
        // Normal move: nothing (free for rubber band selection)
        if loupeEnabled && !loupeLocked && loupePosition != nil {
            let optionPressed = event.modifierFlags.contains(.option)

            if optionPressed {
                // Option held: move crosshairs (what's being magnified)
                loupePosition = location
                needsDisplay = true
            }
            // Normal move does nothing - loupe stays where it is
        }

        // Update cursor for loupe edge resize
        if loupeEnabled, let viewPos = loupeViewPosition {
            let rect = loupeRect(at: viewPos)
            if rect.contains(location) && isOnLoupeEdge(location, loupeCenter: viewPos) {
                NSCursor.crosshair.set()
            } else {
                NSCursor.arrow.set()
            }
        }

        // Normalize to 0-1 range
        let normalizedX = location.x / bounds.width
        let normalizedY = location.y / bounds.height

        onCursorMoved?(CGPoint(x: normalizedX, y: normalizedY))
    }

    private func loupeRect(at position: CGPoint) -> NSRect {
        return NSRect(
            x: position.x - loupeSize / 2,
            y: position.y - loupeSize / 2,
            width: loupeSize,
            height: loupeSize
        )
    }

    /// Check if point is on the edge of the loupe (for resize)
    private func isOnLoupeEdge(_ point: CGPoint, loupeCenter: CGPoint) -> Bool {
        let distance = hypot(point.x - loupeCenter.x, point.y - loupeCenter.y)
        let radius = loupeSize / 2
        // On edge if within threshold of the circle's radius
        return distance >= (radius - edgeThreshold) && distance <= (radius + edgeThreshold)
    }

    /// Distance from point to loupe center
    private func distanceToLoupeCenter(_ point: CGPoint, loupeCenter: CGPoint) -> CGFloat {
        return hypot(point.x - loupeCenter.x, point.y - loupeCenter.y)
    }

    override func mouseDown(with event: NSEvent) {
        guard loupeEnabled else {
            super.mouseDown(with: event)
            return
        }

        let clickLocation = convert(event.locationInWindow, from: nil)

        // Check if clicking on existing loupe
        if let viewPos = loupeViewPosition {
            let rect = loupeRect(at: viewPos)
            if rect.contains(clickLocation) {
                // Check if on edge for resize (works whether locked or not)
                if isOnLoupeEdge(clickLocation, loupeCenter: viewPos) {
                    isResizingLoupe = true
                    resizeStartSize = loupeSize
                    resizeStartDistance = distanceToLoupeCenter(clickLocation, loupeCenter: viewPos)
                    return
                }

                // Not on edge - start dragging to reposition loupe view
                isDraggingLoupe = true
                dragOffset = CGSize(
                    width: clickLocation.x - viewPos.x,
                    height: clickLocation.y - viewPos.y
                )
                return
            }
        }

        // Click outside loupe - pass through for rubber band selection
        super.mouseDown(with: event)
    }

    override func mouseDragged(with event: NSEvent) {
        guard loupeEnabled else {
            super.mouseDragged(with: event)
            return
        }

        let location = convert(event.locationInWindow, from: nil)

        if isResizingLoupe, let viewPos = loupeViewPosition {
            // Resize based on distance from center
            let currentDistance = distanceToLoupeCenter(location, loupeCenter: viewPos)
            let newSize = resizeStartSize * (currentDistance / resizeStartDistance)
            loupeSize = max(minLoupeSize, min(maxLoupeSize, newSize))
            onLoupeSizeChanged?(loupeSize)
            needsDisplay = true
            return
        }

        if isDraggingLoupe {
            // Move only the view position (where loupe is displayed)
            // Crosshairs (what we're looking at) stays the same - use Option+move to change that
            loupeViewPosition = CGPoint(
                x: location.x - dragOffset.width,
                y: location.y - dragOffset.height
            )
            needsDisplay = true
            return
        }

        super.mouseDragged(with: event)
    }

    override func mouseUp(with event: NSEvent) {
        if isDraggingLoupe {
            isDraggingLoupe = false
        } else if isResizingLoupe {
            isResizingLoupe = false
        } else {
            super.mouseUp(with: event)
        }
    }

    override func rightMouseDown(with event: NSEvent) {
        // Right-click to remove loupe
        if loupeEnabled && loupePosition != nil {
            loupePosition = nil
            loupeViewPosition = nil
            needsDisplay = true
            return
        }
        super.rightMouseDown(with: event)
    }

    override func scrollWheel(with event: NSEvent) {
        // Check if cursor is over the loupe
        if loupeEnabled, let viewPos = loupeViewPosition {
            let location = convert(event.locationInWindow, from: nil)
            let rect = loupeRect(at: viewPos)

            if rect.contains(location) {
                // Cursor is over loupe - zoom loupe magnification
                let delta = event.scrollingDeltaY
                let newMag = loupeMagnification + delta * 0.05
                loupeMagnification = max(minLoupeMagnification, min(maxLoupeMagnification, newMag))
                onLoupeMagnificationChanged?(loupeMagnification)
                return
            }
        }
        // Cursor not over loupe - pass to scroll view for image pan/zoom
        super.scrollWheel(with: event)
    }

    // magnify(with:) is NOT overridden - we use gesture recognizers instead
    // to avoid conflicts between event handling and gesture recognition

    // swiftlint:disable function_body_length
    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)

        // Draw loupe if enabled and positioned
        guard loupeEnabled,
              let targetPosition = loupePosition,
              let viewPosition = loupeViewPosition,
              let image = image else { return }

        let rect = loupeRect(at: viewPosition)

        NSGraphicsContext.current?.saveGraphicsState()

        // Draw shadow
        let shadow = NSShadow()
        shadow.shadowColor = NSColor.black.withAlphaComponent(0.5)
        shadow.shadowOffset = NSSize(width: 0, height: -3)
        shadow.shadowBlurRadius = 10
        shadow.set()

        // Clip to circle
        let path = NSBezierPath(ovalIn: rect)
        path.addClip()

        // Draw white background
        NSColor.white.setFill()
        path.fill()

        // Calculate source rect - use target position (what we're looking at)
        let sourceSize = loupeSize / loupeMagnification

        let sourceRect = NSRect(
            x: targetPosition.x - sourceSize / 2,
            y: targetPosition.y - sourceSize / 2,
            width: sourceSize,
            height: sourceSize
        )

        // Draw magnified image
        image.draw(in: rect, from: sourceRect, operation: .sourceOver, fraction: 1.0)

        // Draw border
        NSColor.white.setStroke()
        let borderPath = NSBezierPath(ovalIn: rect.insetBy(dx: 2, dy: 2))
        borderPath.lineWidth = 3
        borderPath.stroke()

        // Draw crosshair
        NSColor.black.withAlphaComponent(0.3).setStroke()
        let centerX = rect.midX
        let centerY = rect.midY
        let crosshairSize: CGFloat = 10

        let crosshair = NSBezierPath()
        crosshair.move(to: NSPoint(x: centerX - crosshairSize, y: centerY))
        crosshair.line(to: NSPoint(x: centerX + crosshairSize, y: centerY))
        crosshair.move(to: NSPoint(x: centerX, y: centerY - crosshairSize))
        crosshair.line(to: NSPoint(x: centerX, y: centerY + crosshairSize))
        crosshair.lineWidth = 1
        crosshair.stroke()

        NSGraphicsContext.current?.restoreGraphicsState()

        // Draw badge showing magnification and size hint
        let badgeText = String(format: "%.1fx · %dpx", loupeMagnification, Int(loupeSize))
        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 9, weight: .medium),
            .foregroundColor: NSColor.white
        ]
        let textSize = (badgeText as NSString).size(withAttributes: attributes)
        let badgePadding: CGFloat = 4
        let badgeWidth = textSize.width + badgePadding * 2
        let badgeHeight = textSize.height + badgePadding

        let badgeRect = NSRect(
            x: rect.midX - badgeWidth / 2,
            y: rect.minY + 8,
            width: badgeWidth,
            height: badgeHeight
        )

        // Badge background
        let badgePath = NSBezierPath(roundedRect: badgeRect, xRadius: 4, yRadius: 4)
        NSColor.black.withAlphaComponent(0.7).setFill()
        badgePath.fill()

        // Badge text
        let textRect = NSRect(
            x: badgeRect.origin.x + badgePadding,
            y: badgeRect.origin.y + (badgeHeight - textSize.height) / 2,
            width: textSize.width,
            height: textSize.height
        )
        (badgeText as NSString).draw(in: textRect, withAttributes: attributes)

        // Draw lock indicator when locked (top of loupe)
        if loupeLocked {
            let lockIconSize: CGFloat = 16
            let lockRect = NSRect(
                x: rect.midX - lockIconSize / 2,
                y: rect.maxY - lockIconSize - 8,
                width: lockIconSize,
                height: lockIconSize
            )

            // Lock background
            let lockBgPath = NSBezierPath(roundedRect: lockRect, xRadius: 4, yRadius: 4)
            NSColor.controlAccentColor.setFill()
            lockBgPath.fill()

            // Draw lock symbol
            if let lockImage = NSImage(systemSymbolName: "lock.fill", accessibilityDescription: nil) {
                let config = NSImage.SymbolConfiguration(pointSize: 10, weight: .medium)
                let configuredImage = lockImage.withSymbolConfiguration(config) ?? lockImage
                configuredImage.draw(
                    in: lockRect.insetBy(dx: 3, dy: 3),
                    from: .zero,
                    operation: .sourceOver,
                    fraction: 1.0
                )
            }
        }
    }
    // swiftlint:enable function_body_length
}

// swiftlint:enable file_length
