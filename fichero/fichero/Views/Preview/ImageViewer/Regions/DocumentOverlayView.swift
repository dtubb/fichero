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
        didSet {
            guard overlay != oldValue else { return }
            needsDisplay = true
            setAccessibilityIdentifier(overlay.documentId.map { SegmentBoxAccessibility.pagePrefix + $0 })
        }
    }

    /// The box under the pointer, in this view's coordinates, or nil.
    private var hovered: CGRect? {
        didSet { if hovered != oldValue { needsDisplay = true } }
    }

    override var isFlipped: Bool { false }  // the image view's own space: y grows upward
    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    // MARK: - Every drawn box is an accessibility element (#5192)

    /// One element per box DRAWN -- in the visible part of the view, from a segment -- identified
    /// `SegmentBox-<segmentId>`, with its frame, its kind, and whether it is selected. What AppleScript,
    /// XCUITest and VoiceOver see is what the window drew: none without a box, no box without one.
    override func accessibilityChildren() -> [Any]? {
        guard let imageRect else { return [] }
        let selected = Set(overlay.selected)
        return overlay.boxes(in: visibleRect, imageRect: imageRect).compactMap { box, rect in
            box.segmentId.map { id in
                SegmentBoxAccessibility.element(
                    segmentId: id, kind: box.kind, frame: rect, in: self, selected: selected.contains(box.bbox)
                )
            }
        }
    }

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
        // The hover's tracking area, installed as the view joins its window (#5411): mounted into an image
        // view already on screen, nothing guarantees AppKit asks `updateTrackingAreas` before the page
        // next scrolls or resizes, and until then resting on a line highlighted nothing.
        updateTrackingAreas()
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

    /// The smallest box containing `point` -- the same "smallest wins" the click path uses, and the hover
    /// label's (`DocumentOverlay.smallestContaining`, #5411).
    private func boxRect(at point: CGPoint) -> CGRect? {
        guard let imageRect else { return nil }
        let rects = overlay.boxes(in: CGRect(origin: point, size: CGSize(width: 0.001, height: 0.001)),
                                  imageRect: imageRect).map(\.rect)
        return DocumentOverlay.smallestContaining(point, in: rects).map { rects[$0] }
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

    /// Every level at once, each inside its parent and lighter than it (ruled 2026-10-05, hierarchy A, #5426):
    /// a region as a faint wash of its hue and a thin outline, its lines as thin outlines in their reading-order
    /// shade, words and letters as hairlines in their line's shade (`SegmentHierarchy`). A selection lights its
    /// children, shows its parent at full strength and dims the rest. Only a region fills at rest; hover and
    /// selection keep their own look (#5207).
    private func drawBoxes(in dirtyRect: NSRect, imageRect: CGRect, scale: CGFloat, line: CGFloat) {
        let finest = overlay.finestLevel
        let emphasis = overlay.emphasis
        for (box, rect) in overlay.boxes(in: dirtyRect, imageRect: imageRect) {
            let level = SegmentHierarchy.Level(kind: box.kind)
            let shown = box.segmentId.flatMap { emphasis[$0] } ?? .rest
            let strength = CGFloat(SegmentHierarchy.strokeOpacity(
                level: level, toneStrength: box.tone?.strength ?? 1, emphasis: shown
            ))
            // The tone carries the hue; its own strength is already in `strength`, so it is applied at 1 here.
            let hue = box.tone.map { RegionColours.Tone(hue: $0.hue, strength: 1) }
            let colour = { (opacity: CGFloat) in SelectionStyle.regionColour(hue, opacity: opacity * strength) }
            let width = line * CGFloat(SegmentHierarchy.widthFactor(level))
            let wash = SegmentHierarchy.washOpacity(level: level, emphasis: shown)
            if wash > 0, box.shapes.isEmpty {
                SelectionStyle.regionColour(hue, opacity: CGFloat(wash)).setFill()
                NSBezierPath(rect: rect).fill()
            }
            // Only the finest level drawn sets its reading inline (#5411, #5426).
            let setsText = box.showsText && !box.text.isEmpty
                && DocumentOverlay.setsTextInline(kind: box.kind, finest: finest)
            // A segment with its own shapes is drawn AS them -- the outline its file drew, the baseline
            // under its ink -- never as the box around them (#5163's residue).
            if !box.shapes.isEmpty, !setsText {
                ShapeDrawing.draw(box.shapes, imageRect: imageRect, scale: scale, look: .init(
                    line: width,
                    stroke: colour(OCRBoxConfidence.strokeOpacity(box.confidence)),
                    // A region drawn as its outline keeps its faint wash, inside the outline.
                    wash: wash > 0 ? SelectionStyle.regionColour(hue, opacity: CGFloat(wash)) : .clear,
                    dashed: box.noReading || OCRBoxConfidence.isUncertain(box.confidence)
                ))
                continue
            }
            if box.noReading {
                // No reading yet: hollow and dashed, never hidden, so it can be seen, picked and typed.
                let hollow = NSBezierPath(rect: rect)
                colour(1).setStroke()
                hollow.lineWidth = width
                hollow.setLineDash([4 / scale, 3 / scale], count: 2, phase: 0)
                hollow.stroke()
                continue
            }
            let path = NSBezierPath(rect: rect)
            if setsText {
                // A theme-matched plate so the word reads, translucent so the scan stays checkable.
                NSColor.textBackgroundColor.withAlphaComponent(InlineWords.plateAlpha).setFill()
                path.fill()
                InlineWords.draw(box.text, direction: box.direction, in: rect)
            }
            colour(OCRBoxConfidence.strokeOpacity(box.confidence)).setStroke()
            path.lineWidth = width
            if OCRBoxConfidence.isUncertain(box.confidence) {
                path.setLineDash([3 / scale, 2 / scale], count: 2, phase: 0)
            }
            path.stroke()
        }
    }

    /// The hovered box: its wash and outline -- a fill only here and on selection, never at rest (#5207).
    private func drawHover(_ rect: CGRect, line: CGFloat) {
        let path = NSBezierPath(rect: rect)
        SelectionStyle.hoverBase.withAlphaComponent(SelectionStyle.hoverWashAlpha).setFill()
        path.fill()
        SelectionStyle.hoverBase.withAlphaComponent(SelectionStyle.hoverAlpha).setStroke()
        path.lineWidth = line
        path.stroke()
    }

    /// The hover, the Inspector's selected annotation, and the selected boxes (with their handles
    /// while editing) -- all in the selection's own style.
    private func drawSelection(
        in dirtyRect: NSRect, imageRect: CGRect, scale: CGFloat, line: CGFloat, emphasized: Bool
    ) {
        let selected = overlay.selected(in: dirtyRect, imageRect: imageRect)
        if let hovered, hovered.intersects(dirtyRect), !selected.contains(hovered) {
            drawHover(hovered, line: line)
        }
        let stroke = SelectionStyle.stroke(emphasized: emphasized)
        let wash = SelectionStyle.washBase(emphasized: emphasized)
            .withAlphaComponent(SelectionStyle.washAlpha(emphasized: emphasized))
        // In Edit Segments the selection is Preview's marquee (#5215): dashed, with eight handles.
        let dashed = overlay.isEditing
        let outline = { (rect: CGRect) in
            let path = NSBezierPath(rect: rect)
            wash.setFill()
            path.fill()
            stroke.setStroke()
            path.lineWidth = line
            if dashed { path.setLineDash([4 / scale, 3 / scale], count: 2, phase: 0) }
            path.stroke()
        }
        // The Inspector's selected annotation: the same selection look as a selected box.
        if let bbox = overlay.selectedMark,
           let rect = DocumentBoxMapping.rect(normalized: bbox, imageRect: imageRect), rect.intersects(dirtyRect) {
            outline(rect)
        }
        // Handles only for ONE selected box, as in Preview (#5236): with several, each is marked and the
        // set moves together; 27 boxes of 8 handles each was a wall of dots.
        let handles = overlay.isEditing && selected.count == 1
        for (index, rect) in selected.enumerated() {
            let shapes = overlay.selectedShapes.indices.contains(index) ? overlay.selectedShapes[index] : []
            if !shapes.isEmpty {
                // Outlined as itself; in Edit Segments, a handle per point and one per side (Reshape).
                ShapeDrawing.draw(shapes, imageRect: imageRect, scale: scale, look: .init(
                    line: line * 1.5, stroke: stroke, wash: wash, dashed: false
                ))
                if handles {
                    ShapeDrawing.drawHandles(shapes, imageRect: imageRect, scale: scale, line: line, stroke: stroke)
                    // The frame around the shape too, whose handles scale every point (#5215).
                    drawFrameHandles(around: rect, scale: scale, line: line, stroke: stroke)
                    if let point = overlay.selectedPoint.flatMap({ DocumentBoxMapping.point(normalized: $0, imageRect: imageRect) }) {
                        // The point the arrow keys nudge: its handle filled, as a selected handle is in Preview.
                        let side = SelectionStyle.handleSide / scale
                        stroke.setFill()
                        NSBezierPath(rect: CGRect(x: point.x - side / 2, y: point.y - side / 2, width: side, height: side)).fill()
                    }
                }
                continue
            }
            outline(rect)
            guard handles else { continue }  // handles only in Edit Segments, on a single selection
            drawFrameHandles(around: rect, scale: scale, line: line, stroke: stroke)
        }
    }

    /// The eight resize handles of a selected box or shape frame, as Preview draws them.
    private func drawFrameHandles(around rect: CGRect, scale: CGFloat, line: CGFloat, stroke: NSColor) {
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

/// A drawn segment box as an accessibility element (#5192): the image overlay and a PDF page make
/// them the same way, so a test or a script asks both surfaces one question.
enum SegmentBoxAccessibility {
    static let identifierPrefix = "SegmentBox-"
    /// The view a page's boxes are drawn in, named for its page (#5193).
    static let pagePrefix = "SegmentPage-"

    static func element(
        segmentId: String, kind: String, frame: CGRect, in parent: NSView, selected: Bool
    ) -> NSAccessibilityElement {
        let element = NSAccessibilityElement()
        element.setAccessibilityRole(.group)
        element.setAccessibilityIdentifier(identifierPrefix + segmentId)
        element.setAccessibilityLabel(kind.capitalized)
        element.setAccessibilityParent(parent)
        element.setAccessibilityFrameInParentSpace(frame)
        element.setAccessibilitySelected(selected)
        return element
    }
}
#endif
