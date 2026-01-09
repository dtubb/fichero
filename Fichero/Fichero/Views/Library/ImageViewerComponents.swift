import SwiftUI
import AppKit

// MARK: - Zoomable Image Preview (with controls and magnifier)

struct ZoomableImagePreview: View {
    let url: URL

    // These settings persist across image changes using AppStorage
    @AppStorage("imagePreview.magnifierEnabled") private var magnifierEnabled = false
    @AppStorage("imagePreview.loupeEnabled") private var loupeEnabled = false
    @AppStorage("imagePreview.loupeMagnification") private var loupeMagnification: Double = 3.0
    @AppStorage("imagePreview.loupeSize") private var loupeSize: Double = 150.0
    @AppStorage("imagePreview.panelMagnification") private var panelMagnification: Double = 4.0
    @AppStorage("imagePreview.panelHeight") private var panelHeight: Double = 120.0
    @AppStorage("imagePreview.magnifierLocked") private var magnifierLocked = false

    @State private var scale: CGFloat = 1.0
    @State private var minScale: CGFloat = 0.1
    @State private var maxScale: CGFloat = 10.0
    @State private var cursorPosition: CGPoint = .zero
    @State private var lastImagePosition: CGPoint = CGPoint(x: 0.5, y: 0.5)  // Last position over image (not UI)
    @State private var lockedPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)  // Position when locked
    @State private var imageSize: CGSize = .zero
    @State private var image: NSImage?
    @State private var visibleRect: CGRect = .zero  // Normalized 0-1

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
                Button(action: { magnifierEnabled.toggle() }) {
                    Image(systemName: "rectangle.bottomhalf.inset.filled")
                }
                .buttonStyle(.plain)
                .foregroundColor(magnifierEnabled ? .accentColor : .primary)
                .help("Magnifier Panel")

                // Loupe toggle with zoom controls
                HStack(spacing: 4) {
                    Button(action: { loupeEnabled.toggle() }) {
                        Image(systemName: loupeEnabled ? "magnifyingglass.circle.fill" : "magnifyingglass.circle")
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(loupeEnabled ? .accentColor : .primary)
                    .help("Loupe (click to place, drag to move, scroll/pinch to zoom, drag edge to resize)")

                    if loupeEnabled {
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
                        loupeMagnification: Binding(
                            get: { CGFloat(loupeMagnification) },
                            set: { loupeMagnification = Double($0) }
                        ),
                        loupeSize: Binding(
                            get: { CGFloat(loupeSize) },
                            set: { loupeSize = Double($0) }
                        ),
                        onImagePositionChanged: { pos in
                            lastImagePosition = pos
                        }
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
                                    // Locking - save last valid image position
                                    lockedPosition = lastImagePosition
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
                        cursorPosition: cursorPosition,
                        visibleRect: visibleRect
                    )
                    .frame(width: 150, height: 100)
                    .padding(8)
                }
            }
        }
        .onAppear {
            image = NSImage(contentsOf: url)
            if let img = image {
                imageSize = img.size
            }
        }
        .onChange(of: url) { _, newURL in
            image = NSImage(contentsOf: newURL)
            if let img = image {
                imageSize = img.size
            }
        }
    }

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
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = 1.0
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
    let url: URL
    @Binding var scale: CGFloat
    @Binding var cursorPosition: CGPoint  // Normalized 0-1 position in image
    @Binding var imageSize: CGSize
    @Binding var visibleRect: CGRect  // Normalized 0-1 visible area
    let minScale: CGFloat
    let maxScale: CGFloat
    let loupeEnabled: Bool
    @Binding var loupeMagnification: CGFloat
    @Binding var loupeSize: CGFloat
    var onImagePositionChanged: ((CGPoint) -> Void)?  // Called when cursor moves over image

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = true
        scrollView.allowsMagnification = true
        scrollView.minMagnification = minScale
        scrollView.maxMagnification = maxScale
        scrollView.magnification = scale
        scrollView.backgroundColor = NSColor(white: 0.15, alpha: 1.0)
        scrollView.postsBoundsChangedNotifications = true

        // Add magnification gesture recognizer for pinch-to-zoom
        let magnifyGesture = NSMagnificationGestureRecognizer(
            target: context.coordinator,
            action: #selector(Coordinator.handleMagnify(_:))
        )
        scrollView.addGestureRecognizer(magnifyGesture)
        context.coordinator.magnifyGesture = magnifyGesture

        // Create tracking image view with loupe
        let imageView = TrackingImageView()
        imageView.imageScaling = .scaleNone  // We'll handle sizing
        imageView.onCursorMoved = { normalizedPos in
            Task { @MainActor in
                self.cursorPosition = normalizedPos
                self.onImagePositionChanged?(normalizedPos)
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
            Task { @MainActor in
                self.imageSize = image.size
            }
        }

        scrollView.documentView = imageView
        context.coordinator.scrollView = scrollView
        context.coordinator.imageView = imageView

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

        // Center initially
        Task { @MainActor in
            self.centerImage(scrollView: scrollView, imageView: imageView)
        }

        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        if abs(scrollView.magnification - scale) > 0.01 {
            scrollView.magnification = scale
        }

        if let imageView = context.coordinator.imageView as? TrackingImageView {
            imageView.loupeEnabled = loupeEnabled
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
        Coordinator()
    }

    private func centerImage(scrollView: NSScrollView, imageView: NSView) {
        guard let imgView = imageView as? NSImageView, let image = imgView.image else { return }

        let viewSize = scrollView.bounds.size
        let imageSize = image.size

        let scaleX = viewSize.width / imageSize.width
        let scaleY = viewSize.height / imageSize.height
        let fitScale = min(scaleX, scaleY, 1.0)

        scrollView.magnification = fitScale
    }

    class Coordinator: NSObject {
        var scrollView: NSScrollView?
        var imageView: NSView?
        var currentURL: URL?
        var onVisibleRectChanged: ((CGRect) -> Void)?
        var magnifyGesture: NSMagnificationGestureRecognizer?
        private var initialMagnification: CGFloat = 1.0

        @objc func boundsDidChange(_ notification: Notification) {
            updateVisibleRect()
        }

        @objc func handleMagnify(_ gesture: NSMagnificationGestureRecognizer) {
            guard let scrollView = scrollView else { return }

            // Check if cursor is over loupe - if so, zoom the loupe instead
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
                    return
                }
            }

            // Not over loupe - zoom main image
            switch gesture.state {
            case .began:
                initialMagnification = scrollView.magnification
            case .changed:
                let newMag = initialMagnification * (1 + gesture.magnification)
                let clampedMag = max(scrollView.minMagnification, min(scrollView.maxMagnification, newMag))
                let location = gesture.location(in: scrollView)
                scrollView.setMagnification(clampedMag, centeredAt: location)
            case .ended, .cancelled:
                break
            default:
                break
            }
        }

        func updateVisibleRect() {
            guard let scrollView = scrollView,
                  let imageView = imageView as? NSImageView,
                  let image = imageView.image else { return }

            let visibleRect = scrollView.contentView.documentVisibleRect
            let imageSize = image.size
            let magnification = scrollView.magnification

            // Calculate scaled image size
            let scaledWidth = imageSize.width * magnification
            let scaledHeight = imageSize.height * magnification

            // Calculate normalized visible rect (0-1 range)
            let normalizedX = visibleRect.origin.x / scaledWidth
            let normalizedWidth = min(1.0, visibleRect.width / scaledWidth)
            let normalizedHeight = min(1.0, visibleRect.height / scaledHeight)

            // For Y, flip because NSScrollView origin is bottom-left but minimap expects top-left origin
            let normalizedY = 1.0 - (visibleRect.origin.y / scaledHeight) - normalizedHeight

            let rect = CGRect(
                x: max(0, min(1 - normalizedWidth, normalizedX)),
                y: max(0, min(1 - normalizedHeight, normalizedY)),
                width: normalizedWidth,
                height: normalizedHeight
            )

            onVisibleRectChanged?(rect)
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
            if loupeEnabled {
                if loupePosition == nil {
                    // Auto-show loupe at center when enabled for the first time
                    showLoupeAtCenter()
                } else {
                    // Re-show at last position
                    needsDisplay = true
                }
            } else {
                // Hide loupe when disabled (but remember position)
                needsDisplay = true
            }
        }
    }
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

        // Update cursor for loupe edge resize
        if loupeEnabled, let viewPos = loupeViewPosition {
            let rect = loupeRect(at: viewPos)
            if rect.contains(location) && isOnLoupeEdge(location, loupeCenter: viewPos) {
                // On edge - show resize cursor
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
                // Check if on edge for resize
                if isOnLoupeEdge(clickLocation, loupeCenter: viewPos) {
                    // Start resizing
                    isResizingLoupe = true
                    resizeStartSize = loupeSize
                    resizeStartDistance = distanceToLoupeCenter(clickLocation, loupeCenter: viewPos)
                    return
                }

                // Not on edge - start dragging
                isDraggingLoupe = true
                dragOffset = CGSize(
                    width: clickLocation.x - viewPos.x,
                    height: clickLocation.y - viewPos.y
                )
                return
            }
        }

        // Place new loupe - both the view position and what it's looking at
        loupePosition = clickLocation
        loupeViewPosition = clickLocation
        needsDisplay = true
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
            // Move only the view position, keep looking at the same spot
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
    }
    // swiftlint:enable function_body_length
}

// swiftlint:enable file_length
