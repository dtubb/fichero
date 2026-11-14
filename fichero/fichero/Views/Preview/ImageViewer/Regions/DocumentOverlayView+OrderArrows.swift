#if os(macOS)
import SwiftUI

extension DocumentOverlayView {
    /// A thin arrowed line from each numbered line to the next (`segment-editor.order-overlay`), under the numbers.
    func drawOrderArrows(imageRect: CGRect, scale: CGFloat) {
        NSColor.secondaryLabelColor.withAlphaComponent(0.7).setStroke()
        for arrow in overlay.orderArrows() {
            guard let from = DocumentBoxMapping.rect(normalized: arrow.from + [1e-6, 1e-6], imageRect: imageRect)?.origin,
                  let tip = DocumentBoxMapping.rect(normalized: arrow.to + [1e-6, 1e-6], imageRect: imageRect)?.origin,
                  from != tip else { continue }
            let path = NSBezierPath()
            path.lineWidth = 1 / scale
            path.move(to: from)
            path.line(to: tip)
            // The head: two short strokes back from the tip, either side of the line.
            let angle = atan2(tip.y - from.y, tip.x - from.x), head = 6 / scale
            for side in [-0.5, 0.5] {
                path.move(to: tip)
                path.line(to: CGPoint(x: tip.x - head * cos(angle + side), y: tip.y - head * sin(angle + side)))
            }
            path.stroke()
        }
    }
}
#endif
