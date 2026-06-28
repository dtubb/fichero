import SwiftUI

/// Draws saved bounding-box annotations over a reader and, in draw mode, lets
/// the user drag a new box (#2458). Coordinate math lives in
/// `BoundingBoxGeometry`; this view is the thin SwiftUI layer over it.
///
/// Reusable across the image reader (and PDF page regions later). The host
/// supplies the normalized boxes + the current visible window and owns
/// persistence via the closure.
struct BoundingBoxOverlay: View {
    /// Saved annotation regions as normalized `[x, y, w, h]` image rects.
    let boxes: [[Double]]
    /// Normalized sub-rect of the image currently visible (zoom/pan window).
    let visible: CGRect
    /// True while the region tool is armed — enables drawing + hit testing.
    let isDrawing: Bool
    /// Called with a normalized `[x, y, w, h]` when the user finishes a drag.
    var onCreate: ([Double]) -> Void

    @State private var dragStart: CGPoint?
    @State private var dragCurrent: CGPoint?

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .topLeading) {
                // Saved regions.
                ForEach(Array(boxes.enumerated()), id: \.offset) { _, box in
                    if let rect = BoundingBoxGeometry.viewRect(normalized: box, in: geo.size, visible: visible) {
                        RoundedRectangle(cornerRadius: 2)
                            .stroke(Color.accentColor, lineWidth: 1.5)
                            .background(Color.accentColor.opacity(0.12))
                            .frame(width: rect.width, height: rect.height)
                            .offset(x: rect.minX, y: rect.minY)
                            .allowsHitTesting(false)
                    }
                }

                // In-progress drag rectangle.
                if let start = dragStart, let current = dragCurrent {
                    let rect = CGRect(
                        x: min(start.x, current.x),
                        y: min(start.y, current.y),
                        width: abs(current.x - start.x),
                        height: abs(current.y - start.y)
                    )
                    RoundedRectangle(cornerRadius: 2)
                        .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 1.5, dash: [4]))
                        .background(Color.accentColor.opacity(0.15))
                        .frame(width: rect.width, height: rect.height)
                        .offset(x: rect.minX, y: rect.minY)
                        .allowsHitTesting(false)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .contentShape(Rectangle())
            .gesture(isDrawing ? drawGesture(in: geo.size) : nil)
        }
    }

    private func drawGesture(in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 1)
            .onChanged { value in
                if dragStart == nil { dragStart = value.startLocation }
                dragCurrent = value.location
            }
            .onEnded { value in
                defer { dragStart = nil; dragCurrent = nil }
                let start = dragStart ?? value.startLocation
                if let box = BoundingBoxGeometry.normalizedBox(
                    from: start, to: value.location, in: size, visible: visible
                ) {
                    onCreate(box)
                }
            }
    }
}
