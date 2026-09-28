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
        // observers need no removal when the view goes (macOS 10.11 and later). Removed BY NAME:
        // only this view's own look observers, never anything else registered for it.
        let center = NotificationCenter.default
        for name in [NSWindow.didBecomeKeyNotification, NSWindow.didResignKeyNotification,
                     NSColor.systemColorsDidChangeNotification] {
            center.removeObserver(self, name: name, object: nil)
        }
        NSWorkspace.shared.notificationCenter.removeObserver(
            self, name: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification, object: nil
        )
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

    /// Ephemeral marquees: dashed accent, visually distinct from a saved region; the picked one solid.
    private func drawMarquees(in dirtyRect: CGRect, imageRect: CGRect, scale: CGFloat) {
        for (index, bbox) in overlay.marquees.enumerated() {
            guard let rect = DocumentBoxMapping.rect(normalized: bbox, imageRect: imageRect),
                  rect.insetBy(dx: -2 / scale, dy: -2 / scale).intersects(dirtyRect) else { continue }
            let picked = overlay.pickedMarquee == index
            let path = NSBezierPath(rect: rect)
            SelectionStyle.boxBase.withAlphaComponent(picked ? 0.18 : 0.08).setFill()
            path.fill()
            SelectionStyle.boxBase.setStroke()
            path.lineWidth = (picked ? 2 : 1.5) / scale
            if !picked { path.setLineDash([5 / scale, 5 / scale], count: 2, phase: 0) }
            path.stroke()
        }
    }

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

        drawWashes(in: dirtyRect, imageRect: imageRect, scale: scale, emphasized: emphasized)  // BEHIND the boxes
        drawMarks(in: dirtyRect, imageRect: imageRect, scale: scale)
        drawBoxes(in: dirtyRect, imageRect: imageRect, scale: scale, line: line)
        drawMarquees(in: dirtyRect, imageRect: imageRect, scale: scale)
        drawSelection(in: dirtyRect, imageRect: imageRect, scale: scale, line: line, emphasized: emphasized)
    }

    private func drawWashes(in dirtyRect: NSRect, imageRect: CGRect, scale: CGFloat, emphasized: Bool) {
        NSColor.systemYellow.withAlphaComponent(0.22).setFill()
        for rect in DocumentOverlay.rects(overlay.entryWashes, in: dirtyRect, imageRect: imageRect) {
            NSBezierPath(roundedRect: rect, xRadius: 3 / scale, yRadius: 3 / scale).fill()
        }
        SelectionStyle.washBase(emphasized: emphasized).withAlphaComponent(0.28).setFill()
        for rect in DocumentOverlay.rects(overlay.linkedWashes, in: dirtyRect, imageRect: imageRect) {
            NSBezierPath(roundedRect: rect, xRadius: 2 / scale, yRadius: 2 / scale).fill()
        }
    }

    private func drawBoxes(in dirtyRect: NSRect, imageRect: CGRect, scale: CGFloat, line: CGFloat) {
        for (box, rect) in overlay.boxes(in: dirtyRect, imageRect: imageRect) {
            // A segment with its own shapes is drawn AS them -- the outline its file drew, the baseline
            // under its ink -- never as the box around them (#5163's residue).
            if !box.shapes.isEmpty, !(box.showsText && !box.text.isEmpty) {
                ShapeDrawing.draw(box.shapes, imageRect: imageRect, scale: scale, look: .init(
                    line: line,
                    stroke: SelectionStyle.boxBase.withAlphaComponent(OCRBoxConfidence.strokeOpacity(box.confidence)),
                    wash: SelectionStyle.boxBase.withAlphaComponent(SelectionStyle.boxWashAlpha),
                    dashed: OCRBoxConfidence.isUncertain(box.confidence)
                ))
                continue
            }
            let path = NSBezierPath(rect: rect)
            if box.showsText, !box.text.isEmpty {
                // A theme-matched plate so the word reads, translucent so the scan stays checkable.
                NSColor.textBackgroundColor.withAlphaComponent(InlineWords.plateAlpha).setFill()
                path.fill()
                InlineWords.draw(box.text, in: rect)
            } else {
                SelectionStyle.boxBase.withAlphaComponent(SelectionStyle.boxWashAlpha).setFill()
                path.fill()
            }
            SelectionStyle.boxBase.withAlphaComponent(OCRBoxConfidence.strokeOpacity(box.confidence)).setStroke()
            path.lineWidth = line
            if OCRBoxConfidence.isUncertain(box.confidence) {
                path.setLineDash([3 / scale, 2 / scale], count: 2, phase: 0)
            }
            path.stroke()
        }
    }

    /// The hover, the Inspector's selected annotation, and the selected boxes (with their handles
    /// while editing) -- all in the selection's own style.
    private func drawSelection(
        in dirtyRect: NSRect, imageRect: CGRect, scale: CGFloat, line: CGFloat, emphasized: Bool
    ) {
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
        let outline = { (rect: CGRect) in
            let path = NSBezierPath(rect: rect)
            wash.setFill()
            path.fill()
            stroke.setStroke()
            path.lineWidth = line
            path.stroke()
        }
        // The Inspector's selected annotation: the same selection look as a selected box.
        if let bbox = overlay.selectedMark,
           let rect = DocumentBoxMapping.rect(normalized: bbox, imageRect: imageRect), rect.intersects(dirtyRect) {
            outline(rect)
        }
        for (index, rect) in selected.enumerated() {
            let shapes = overlay.selectedShapes.indices.contains(index) ? overlay.selectedShapes[index] : []
            if !shapes.isEmpty {
                // Outlined as itself; in Edit Segments, a handle per point and one per side (Reshape).
                ShapeDrawing.draw(shapes, imageRect: imageRect, scale: scale, look: .init(
                    line: line * 1.5, stroke: stroke, wash: wash, dashed: false
                ))
                if overlay.isEditing {
                    ShapeDrawing.drawHandles(shapes, imageRect: imageRect, scale: scale, line: line, stroke: stroke)
                }
                continue
            }
            outline(rect)
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

/// A recognised word drawn IN its box, the size of the word it stands for (2026-09-01): the largest
/// size that fits the box in BOTH axes, never truncated. In DOCUMENT space, so it is page ink and
/// scales with the page like the pixels under it.
/// A segment's own shapes as paths in the image view's document space (`SegmentShapes.Drawn`): a
/// polygon closed and washed, a path open, a point a dot, the baseline a heavier line under the ink.
/// Every length is in SCREEN points, divided by the magnification, as the boxes' are.
enum ShapeDrawing {
    /// How the shapes are stroked and washed: a box's look, or the selection's.
    struct Look {
        let line: CGFloat
        let stroke: NSColor
        let wash: NSColor
        let dashed: Bool
    }

    static func draw(_ shapes: [SegmentShapes.Drawn], imageRect: CGRect, scale: CGFloat, look: Look) {
        let (line, stroke, wash, dashed) = (look.line, look.stroke, look.wash, look.dashed)
        for shape in shapes {
            let points = shape.points.compactMap { DocumentBoxMapping.point(normalized: $0, imageRect: imageRect) }
            switch shape {
            case .polygon:
                guard let path = path(through: points, closed: true) else { continue }
                wash.setFill()
                path.fill()
                stroke.setStroke()
                path.lineWidth = line
                if dashed { path.setLineDash([3 / scale, 2 / scale], count: 2, phase: 0) }
                path.stroke()
            case .path:
                guard let path = path(through: points, closed: false) else { continue }
                stroke.setStroke()
                path.lineWidth = line
                path.stroke()
            case .baseline:
                guard let path = path(through: points, closed: false) else { continue }
                stroke.setStroke()
                path.lineWidth = line * 2
                path.lineCapStyle = .round
                path.stroke()
            case .point:
                guard let point = points.first else { continue }
                let radius = 3 / scale
                let dot = NSBezierPath(ovalIn: CGRect(x: point.x - radius, y: point.y - radius,
                                                      width: radius * 2, height: radius * 2))
                stroke.setFill()
                dot.fill()
            }
        }
    }

    /// Reshape's handles: a square on every point of the outline and the baseline, as Preview draws a
    /// shape's handles, and a small round one on each side's midpoint, where a point can be added.
    static func drawHandles(
        _ shapes: [SegmentShapes.Drawn], imageRect: CGRect, scale: CGFloat, line: CGFloat, stroke: NSColor
    ) {
        let side = SelectionStyle.handleSide / scale
        for shape in shapes {
            let target: SegmentShapes.Target
            switch shape {
            case .polygon: target = .polygon
            case .baseline: target = .baseline
            case .path, .point: continue  // not reshaped here yet
            }
            for normalized in shape.points {
                guard let point = DocumentBoxMapping.point(normalized: normalized, imageRect: imageRect) else { continue }
                let square = NSBezierPath(rect: CGRect(x: point.x - side / 2, y: point.y - side / 2, width: side, height: side))
                SelectionStyle.handleFill.setFill()
                square.fill()
                stroke.setStroke()
                square.lineWidth = line
                square.stroke()
            }
            for normalized in SegmentShapes.sideMidpoints(shape.points, target) {
                guard let point = DocumentBoxMapping.point(normalized: normalized, imageRect: imageRect) else { continue }
                let radius = side / 3
                let dot = NSBezierPath(ovalIn: CGRect(x: point.x - radius, y: point.y - radius,
                                                      width: radius * 2, height: radius * 2))
                stroke.setFill()
                dot.fill()
            }
        }
    }

    private static func path(through points: [CGPoint], closed: Bool) -> NSBezierPath? {
        guard let first = points.first, points.count >= 2 else { return nil }
        let path = NSBezierPath()
        path.move(to: first)
        points.dropFirst().forEach { path.line(to: $0) }
        if closed { path.close() }
        return path
    }
}

enum InlineWords {
    static let plateAlpha: CGFloat = 0.6
    /// Leaves a hairline of plate above and below the cap height.
    static let heightFill: CGFloat = 0.82

    /// The font size `text` is drawn at in `rect`: from the box's height, then shrunk (up to three
    /// passes, biased under the box) while it is wider than the box.
    static func fittedSize(_ text: String, in rect: CGRect, measure: (String, CGFloat) -> CGFloat) -> CGFloat {
        var size = max(rect.height * heightFill, 0.5)
        var width = measure(text, size)
        var passes = 0
        while width > rect.width, width > 0, passes < 3 {
            size *= (rect.width / width) * 0.98
            width = measure(text, size)
            passes += 1
        }
        return size
    }

    static func draw(_ text: String, in rect: CGRect) {
        let size = fittedSize(text, in: rect) { string, points in
            (string as NSString).size(withAttributes: [.font: NSFont.systemFont(ofSize: points)]).width
        }
        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: size), .foregroundColor: NSColor.labelColor
        ]
        let measured = (text as NSString).size(withAttributes: attributes)
        let origin = CGPoint(x: rect.minX, y: rect.midY - measured.height / 2)
        (text as NSString).draw(at: origin, withAttributes: attributes)
    }
}
#endif
