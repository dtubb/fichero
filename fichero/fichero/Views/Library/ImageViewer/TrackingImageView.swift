#if canImport(AppKit)
import AppKit

// This class requires a large body due to complex AppKit integration
/// Custom NSImageView with cursor tracking and loupe functionality
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
    private let minLoupeSize: CGFloat = 40
    private let maxLoupeSize: CGFloat = 600
    var loupeMagnification: CGFloat = 3.0 {
        didSet {
            if loupePosition != nil {
                needsDisplay = true
            }
        }
    }
    private let minLoupeMagnification: CGFloat = 0.25
    private let maxLoupeMagnification: CGFloat = 20.0

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

        // Normalize to 0-1 range relative to the actual image, not the frame.
        // When zoomed out, the frame is larger than the image (image is centered),
        // so we subtract the centering offset before normalizing.
        guard let image = image else { return }
        let imageW = image.size.width
        let imageH = image.size.height
        let offsetX = max(0, (bounds.width - imageW) / 2)
        let offsetY = max(0, (bounds.height - imageH) / 2)
        let normalizedX = (location.x - offsetX) / imageW
        let normalizedY = (location.y - offsetY) / imageH

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

        // Calculate source rect - use target position (what we're looking at).
        // loupePosition is stored in view coordinates (which include the centering
        // offset added when the scaled image is smaller than the viewport). Convert
        // to image coordinates before passing to NSImage.draw(in:from:), which
        // expects coordinates in the image's own space (0,0 = bottom-left of image).
        let sourceSize = loupeSize / loupeMagnification
        let imageW = image.size.width
        let imageH = image.size.height
        let offsetX = max(0, (bounds.width - imageW) / 2)
        let offsetY = max(0, (bounds.height - imageH) / 2)
        let imagePos = CGPoint(x: targetPosition.x - offsetX, y: targetPosition.y - offsetY)

        let sourceRect = NSRect(
            x: imagePos.x - sourceSize / 2,
            y: imagePos.y - sourceSize / 2,
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
#elseif canImport(UIKit)
import UIKit

/// iOS stub for the AppKit cursor-tracking image view.
/// The loupe is currently non-functional on iOS; this keeps the API surface
/// identical so `ImageWithCursorTracking` compiles and can fill in behavior
/// in a follow-up without touching macOS.
class TrackingImageView: UIImageView {
    var onCursorMoved: ((CGPoint) -> Void)?
    var onLoupeMagnificationChanged: ((CGFloat) -> Void)?
    var onLoupeSizeChanged: ((CGFloat) -> Void)?
    var loupeEnabled: Bool = false {
        didSet { setNeedsDisplay() }
    }
    var loupeLocked: Bool = false
    var loupePosition: CGPoint?
    var loupeViewPosition: CGPoint?
    var loupeSize: CGFloat = 150 {
        didSet { if loupePosition != nil { setNeedsDisplay() } }
    }
    var loupeMagnification: CGFloat = 3.0 {
        didSet { if loupePosition != nil { setNeedsDisplay() } }
    }

    func showLoupeAtCenter() {
        loupePosition = CGPoint(x: bounds.midX, y: bounds.midY)
        loupeViewPosition = loupePosition
        setNeedsDisplay()
    }
}

#endif

