import SwiftUI

#if os(macOS)  // RegionInteractionLayer is Mac-only (an AppKit event layer)

/// The Shape tool's polygon and baseline in Edit Segments (`source.editor.draw-shapes`): each click adds
/// a point; for a polygon a click on the first point closes it, and for either a double-click finishes.
/// Escape abandons it (`WindowState.abandonDrawing`). The finished points go to the host
/// (`onDrawShapeCommit`), which makes the segment with ⌘Z. A box is
/// still the band's drag, unchanged: this takes no event while the tool draws boxes.
extension RegionInteractionLayer {
    /// The drawing so far, kept on the window so Escape can abandon it (`WindowState.abandonDrawing`).
    var drawingPoints: [[Double]] {
        get { windowState?.drawingPoints ?? [] }
        nonmutating set { windowState?.drawingPoints = newValue }
    }

    /// True when the event belongs to a polygon or baseline drawing (so nothing else acts on it).
    func handleDrawShape(_ event: PreviewPointerEvent, in size: CGSize) -> Bool {
        guard onDrawShapeCommit != nil, drawsSegments, isAddingRegion, drawKind != .box else {
            if !drawingPoints.isEmpty { drawingPoints = [] }  // the tool changed mid-drawing: dropped
            return false
        }
        guard event.phase == .pressed else { return true }  // clicks, not drags, place points
        let point = [Double(event.point.x), Double(event.point.y)]
        let reach = [Double(SelectionStyle.handleSide) / max(size.width, 1) * visible.width,
                     Double(SelectionStyle.handleSide) / max(size.height, 1) * visible.height]
        if event.clickCount >= 2 || (drawKind == .polygon && SegmentShapes.closes(drawingPoints, at: point, tolerance: reach)) {
            finishDrawing()
        } else {
            drawingPoints.append(point)
        }
        return true
    }

    /// Hand the points over when there are enough; too few is dropped (nothing is made of it).
    func finishDrawing() {
        defer { drawingPoints = [] }
        guard drawingPoints.count >= drawKind.minimumPoints else { return }
        onDrawShapeCommit?(drawKind, drawingPoints)
    }

    /// The drawing so far: its points joined, each marked.
    @ViewBuilder
    func liveDrawing(in size: CGSize) -> some View {
        if !drawingPoints.isEmpty, visible.width > 0, visible.height > 0 {
            let points = drawingPoints.map {
                CGPoint(x: ($0[0] - visible.minX) / visible.width * size.width,
                        y: ($0[1] - visible.minY) / visible.height * size.height)
            }
            ZStack(alignment: .topLeading) {
                Path { path in
                    guard let first = points.first else { return }
                    path.move(to: first)
                    points.dropFirst().forEach { path.addLine(to: $0) }
                }
                .stroke(Color.accentColor, style: StrokeStyle(lineWidth: drawKind == .baseline ? 2 : 1.5, dash: [4]))
                ForEach(points.indices, id: \.self) { index in
                    Rectangle()
                        .fill(Color(nsColor: .controlBackgroundColor))
                        .overlay(Rectangle().stroke(Color.accentColor, lineWidth: 1))
                        .frame(width: 6, height: 6)
                        .position(points[index])
                }
            }
        }
    }
}
#endif
