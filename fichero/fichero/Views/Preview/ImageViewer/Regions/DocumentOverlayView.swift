#if os(macOS)
import AppKit

/// The boxes, drawn INSIDE the image view -- the scroll view's document view -- so AppKit's one
/// transform moves them with the pixels, in the same pass (#5020, #5142). Nothing is re-mapped per
/// scroll tick: a scroll shifts what is already drawn and asks this view for the exposed strip only.
///
/// Every colour and width comes from `SelectionStyle`, the system's own selection language: the
/// accent while this pane is the focused one and its window is key, the unemphasized grey otherwise;
/// square handles on a selection only in Edit Segments; a fainter outline under the pointer.
///
/// Never hit-testable: every click and gesture falls through to the image view and the region
/// layer. The pointer is READ through a tracking area, which does not route events.
final class DocumentOverlayView: NSView {
    var overlay: DocumentOverlay = .empty {
        didSet { if overlay != oldValue { needsDisplay = true } }
    }

    /// The box under the pointer, in this view's coordinates, or nil.
    private var hovered: CGRect? {
        didSet { if hovered != oldValue { needsDisplay = true } }
    }

    override var isFlipped: Bool { false }  // the image view's own space: y grows upward
    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    // MARK: - Redraw when the system's look changes

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        // Re-registered on every move, so neither centre holds this view twice. Selector-based
        // observers need no removal when the view goes (macOS 10.11 and later).
        NotificationCenter.default.removeObserver(self)
        NSWorkspace.shared.notificationCenter.removeObserver(self)
        let center = NotificationCenter.default
        for name in [NSWindow.didBecomeKeyNotification, NSWindow.didResignKeyNotification] {
            center.addObserver(self, selector: #selector(systemLookChanged), name: name, object: window)
        }
        center.addObserver(self, selector: #selector(systemLookChanged),
                           name: NSColor.systemColorsDidChangeNotification, object: nil)
        NSWorkspace.shared.notificationCenter.addObserver(
            self, selector: #selector(systemLookChanged),
            name: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification, object: nil
        )
    }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        needsDisplay = true  // Dark Mode: system colours resolve again at draw time
    }

    @objc private func systemLookChanged() { needsDisplay = true }

    // MARK: - Hover, read without taking events

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        trackingAreas.forEach(removeTrackingArea)
        addTrackingArea(NSTrackingArea(
            rect: .zero, options: [.mouseMoved, .mouseEnteredAndExited, .activeInKeyWindow, .inVisibleRect],
            owner: self, userInfo: nil
        ))
    }

    override func mouseMoved(with event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        hovered = boxRect(at: point)
    }

    override func mouseExited(with event: NSEvent) { hovered = nil }

    /// The smallest box containing `point` -- the same "smallest wins" the click path uses.
    private func boxRect(at point: CGPoint) -> CGRect? {
        guard let imageRect else { return nil }
        return overlay.boxes(in: CGRect(origin: point, size: CGSize(width: 0.001, height: 0.001)),
                             imageRect: imageRect)
            .map(\.rect)
            .filter { $0.contains(point) }
            .min { $0.width * $0.height < $1.width * $1.height }
    }

    /// The ONE rule for where the image sits in its view, the same one the pointer path uses.
    private var imageRect: CGRect? {
        guard let host = superview else { return nil }
        let rect = DrawnImageFrame.drawnRect(in: host)
        return rect.width > 0 && rect.height > 0 ? rect : nil
    }

    // MARK: - Drawing

    /// Saved annotation marks, by kind: a highlight is a wash, an underline and a strike are bars, a
    /// line is a line, a legacy region is a box. The person's colour when they chose one.
    private func drawMarks(in dirtyRect: CGRect, imageRect: CGRect, scale: CGFloat) {
        let bar: CGFloat = 2 / scale
        for mark in overlay.marks {
            guard let rect = DocumentBoxMapping.rect(normalized: mark.bbox, imageRect: imageRect),
                  rect.insetBy(dx: -bar, dy: -bar).intersects(dirtyRect) else { continue }
            let chosen = mark.color.map {
                NSColor(srgbRed: $0.red, green: $0.green, blue: $0.blue, alpha: $0.alpha)
            }
            switch mark.shape {
            case .wash:
                let alpha = (mark.color?.alpha ?? 1) < 1 ? (mark.color?.alpha ?? 0.3) : 0.3
                (chosen ?? .systemYellow).withAlphaComponent(alpha).setFill()
                NSBezierPath(rect: rect).fill()
            case .underline:
                // The page's BOTTOM is low y in this unflipped space.
                (chosen ?? .controlAccentColor).setFill()
                NSBezierPath(rect: CGRect(x: rect.minX, y: rect.minY, width: rect.width, height: bar)).fill()
            case .strike:
                (chosen ?? .controlAccentColor).setFill()
                NSBezierPath(rect: CGRect(x: rect.minX, y: rect.midY - bar / 2, width: rect.width, height: bar)).fill()
            case .line:
                // Top-left to bottom-right on the PAGE: high y to low y here.
                let path = NSBezierPath()
                path.move(to: CGPoint(x: rect.minX, y: rect.maxY))
                path.line(to: CGPoint(x: rect.maxX, y: rect.minY))
                path.lineWidth = bar
                (chosen ?? .controlAccentColor).setStroke()
                path.stroke()
            case .box:
                let path = NSBezierPath(rect: rect)
                NSColor.controlAccentColor.withAlphaComponent(0.12).setFill()
                path.fill()
                NSColor.controlAccentColor.setStroke()
                path.lineWidth = 1.5 / scale
                path.stroke()
            }
        }
    }

    override func draw(_ dirtyRect: NSRect) {
        guard let imageRect else { return }
        // Drawn in document points and magnified with the page: divide by the magnification so a
        // line, a corner and a handle keep their SCREEN size at any zoom.
        let scale = max(enclosingScrollView?.magnification ?? 1, 0.01)
        let contrast = NSWorkspace.shared.accessibilityDisplayShouldIncreaseContrast
        let line = SelectionStyle.lineWidth(increaseContrast: contrast) / scale
        let emphasized = overlay.isFocusedPane && (window?.isKeyWindow ?? false)

        // Washes first, BEHIND the boxes.
        NSColor.systemYellow.withAlphaComponent(0.22).setFill()
        for rect in DocumentOverlay.rects(overlay.entryWashes, in: dirtyRect, imageRect: imageRect) {
            NSBezierPath(roundedRect: rect, xRadius: 3 / scale, yRadius: 3 / scale).fill()
        }
        SelectionStyle.washBase(emphasized: emphasized).withAlphaComponent(0.28).setFill()
        for rect in DocumentOverlay.rects(overlay.linkedWashes, in: dirtyRect, imageRect: imageRect) {
            NSBezierPath(roundedRect: rect, xRadius: 2 / scale, yRadius: 2 / scale).fill()
        }

        drawMarks(in: dirtyRect, imageRect: imageRect, scale: scale)

        for (box, rect) in overlay.boxes(in: dirtyRect, imageRect: imageRect) {
            let path = NSBezierPath(rect: rect)
            SelectionStyle.boxBase.withAlphaComponent(SelectionStyle.boxWashAlpha).setFill()
            path.fill()
            SelectionStyle.boxBase.withAlphaComponent(OCRBoxConfidence.strokeOpacity(box.confidence)).setStroke()
            path.lineWidth = line
            if OCRBoxConfidence.isUncertain(box.confidence) {
                path.setLineDash([3 / scale, 2 / scale], count: 2, phase: 0)
            }
            path.stroke()
        }

        let selected = overlay.selected(in: dirtyRect, imageRect: imageRect)
        if let hovered, hovered.intersects(dirtyRect), !selected.contains(hovered) {
            let path = NSBezierPath(rect: hovered)
            SelectionStyle.hoverBase.withAlphaComponent(SelectionStyle.hoverAlpha).setStroke()
            path.lineWidth = line
            path.stroke()
        }

        let stroke = SelectionStyle.stroke(emphasized: emphasized)
        let wash = SelectionStyle.washBase(emphasized: emphasized)
            .withAlphaComponent(SelectionStyle.washAlpha(emphasized: emphasized))
        // The Inspector's selected annotation: the same selection look as a selected box.
        if let bbox = overlay.selectedMark,
           let rect = DocumentBoxMapping.rect(normalized: bbox, imageRect: imageRect), rect.intersects(dirtyRect) {
            let path = NSBezierPath(rect: rect)
            wash.setFill()
            path.fill()
            stroke.setStroke()
            path.lineWidth = line
            path.stroke()
        }
        for rect in selected {
            let path = NSBezierPath(rect: rect)
            wash.setFill()
            path.fill()
            stroke.setStroke()
            path.lineWidth = line
            path.stroke()
            guard overlay.isEditing else { continue }  // handles only in Edit Segments
            for handle in SelectionStyle.handleRects(around: rect, side: SelectionStyle.handleSide / scale) {
                let square = NSBezierPath(rect: handle)
                SelectionStyle.handleFill.setFill()
                square.fill()
                stroke.setStroke()
                square.lineWidth = line
                square.stroke()
            }
        }
    }
}
#endif
