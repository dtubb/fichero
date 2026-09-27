#if os(macOS)
import AppKit
import SwiftUI

/// The boxes, drawn INSIDE the image view -- the scroll view's document view -- so AppKit's one
/// transform moves them with the pixels, in the same pass (#5020, #5142). Nothing is re-mapped per
/// scroll tick: a scroll shifts what is already drawn and asks this view for the exposed strip only.
///
/// Never hit-testable: every click and gesture falls through to the image view and the region
/// layer, exactly as the SwiftUI overlay it replaces did.
final class DocumentOverlayView: NSView {
    var overlay: DocumentOverlay = .empty {
        didSet { if overlay != oldValue { needsDisplay = true } }
    }

    override var isFlipped: Bool { false }  // the image view's own space: y grows upward
    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override func draw(_ dirtyRect: NSRect) {
        let size = bounds.size
        // Strokes are drawn in document points and magnified with the page; divide by the
        // magnification so a line stays one screen point at any zoom.
        let scale = max(enclosingScrollView?.magnification ?? 1, 0.01)
        let wash = NSColor(Color.accentColor).withAlphaComponent(0.08)
        for (box, rect) in overlay.boxes(in: dirtyRect, documentSize: size) {
            let path = NSBezierPath(roundedRect: rect, xRadius: 1.5 / scale, yRadius: 1.5 / scale)
            wash.setFill()
            path.fill()
            NSColor(Color.accentColor)
                .withAlphaComponent(OCRBoxConfidence.strokeOpacity(box.confidence))
                .setStroke()
            path.lineWidth = 1 / scale
            if OCRBoxConfidence.isUncertain(box.confidence) {
                path.setLineDash([3 / scale, 2 / scale], count: 2, phase: 0)
            }
            path.stroke()
        }
        let accent = NSColor(Color.accentColor)
        for rect in overlay.selected(in: dirtyRect, documentSize: size) {
            let path = NSBezierPath(roundedRect: rect, xRadius: 2 / scale, yRadius: 2 / scale)
            accent.withAlphaComponent(0.14).setFill()
            path.fill()
            accent.setStroke()
            path.lineWidth = 2 / scale
            path.stroke()
        }
    }
}
#endif
