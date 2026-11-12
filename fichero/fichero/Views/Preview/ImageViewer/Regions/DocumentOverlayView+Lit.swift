#if os(macOS)
import AppKit

// MARK: - The lit region and the handles

extension DocumentOverlayView {
    /// The region boxes lit by a hovered or selected line: an outline in the region's hue, no wash.
    func drawLitRegions(lighting hovered: String?, in dirtyRect: NSRect, imageRect: CGRect, line: CGFloat) {
        let lit = overlay.litRegions(for: [hovered].compactMap { $0 } + overlay.selectedSegmentIds.sorted())
        for region in lit {
            guard let tone = region.tone, let rect = DocumentBoxMapping.rect(normalized: region.bbox, imageRect: imageRect),
                  rect.intersects(dirtyRect) else { continue }
            let path = NSBezierPath(rect: rect)
            SelectionStyle.regionHue(tone).withAlphaComponent(SelectionStyle.litRegionAlpha).setStroke()
            path.lineWidth = line * 1.5
            path.stroke()
        }
    }

    /// The eight resize handles of a selected box or shape frame, as Preview draws them.
    func drawFrameHandles(around rect: CGRect, scale: CGFloat, line: CGFloat, stroke: NSColor) {
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
#endif
