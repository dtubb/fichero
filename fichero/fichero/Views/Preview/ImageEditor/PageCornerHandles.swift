import SwiftUI

/// The page's four corners, top-left clockwise, in fractions of the upright image (0…1) — the numbers the engine's
/// `square` operation takes (`prep.square.corner-handles-correct-it`). Pure value: the drag maths is tested without a view.
struct PageCorners: Equatable {
    private(set) var points: [CGPoint]

    init?(points: [CGPoint]) {
        guard points.count == 4 else { return nil }
        self.points = points.map { Self.clamped($0) }
    }

    /// The corners of a document's `page_region` metadata (`{"quad": [[x, y] × 4], …}`), nil when it has none.
    init?(pageRegion: Any?) {
        guard let region = pageRegion as? [String: Any],
              let quad = region["quad"] as? [Any], quad.count == 4 else { return nil }
        let points = quad.compactMap { corner -> CGPoint? in
            guard let pair = corner as? [Any], pair.count == 2,
                  let x = (pair[0] as? NSNumber)?.doubleValue, let y = (pair[1] as? NSNumber)?.doubleValue else { return nil }
            return CGPoint(x: x, y: y)
        }
        self.init(points: points)
    }

    func moving(_ index: Int, to point: CGPoint) -> PageCorners {
        var copy = self
        guard copy.points.indices.contains(index) else { return copy }
        copy.points[index] = Self.clamped(point)
        return copy
    }

    /// The wire form of the `square` request's `quad`.
    var quad: [[Double]] { points.map { [Double($0.x), Double($0.y)] } }

    /// The index of the corner nearest `point` within `radius` (same units), nil when the press is on none.
    func corner(near point: CGPoint, radius: CGFloat) -> Int? {
        let hits = points.enumerated().map { ($0.offset, hypot($0.element.x - point.x, $0.element.y - point.y)) }
        return hits.filter { $0.1 <= radius }.min { $0.1 < $1.1 }?.0
    }

    private static func clamped(_ p: CGPoint) -> CGPoint {
        CGPoint(x: min(max(p.x, 0), 1), y: min(max(p.y, 0), 1))
    }
}

/// Four dashed handles on the page's corners, drawn over a fitted image. Drag a corner; Return squares the page
/// from the corrected corners (`who: person`). Geometry lives in `PageCorners`; this only draws and reports.
struct PageCornerHandlesOverlay: View {
    /// The image's frame within the container, in container coordinates.
    let fittedRect: CGRect
    @Binding var corners: PageCorners
    let onSquare: () -> Void

    @State private var dragging: Int?
    private let hitRadius: CGFloat = 0.04

    var body: some View {
        ZStack(alignment: .topLeading) {
            Color.clear.contentShape(Rectangle())
            Path { path in
                let screen = corners.points.map(toScreen)
                path.addLines(screen)
                path.closeSubpath()
            }
            .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 1.5, dash: [6, 4]))
            .allowsHitTesting(false)
            ForEach(Array(corners.points.enumerated()), id: \.offset) { _, point in
                Circle()
                    .strokeBorder(Color.accentColor, style: StrokeStyle(lineWidth: 2, dash: [3, 2]))
                    .background(Circle().fill(Color.accentColor.opacity(0.15)))
                    .frame(width: 18, height: 18)
                    .position(toScreen(point))
                    .allowsHitTesting(false)
            }
        }
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { value in
                    let here = toFraction(value.location)
                    if dragging == nil {
                        dragging = corners.corner(near: toFraction(value.startLocation), radius: hitRadius)
                    }
                    if let index = dragging { corners = corners.moving(index, to: here) }
                }
                .onEnded { _ in dragging = nil }
        )
        .focusable()
        .onKeyPress(.return) { onSquare(); return .handled }
        .accessibilityIdentifier("pageCornerHandles")
    }

    private func toScreen(_ p: CGPoint) -> CGPoint {
        CGPoint(x: fittedRect.minX + p.x * fittedRect.width, y: fittedRect.minY + p.y * fittedRect.height)
    }

    private func toFraction(_ p: CGPoint) -> CGPoint {
        guard fittedRect.width > 0, fittedRect.height > 0 else { return .zero }
        return CGPoint(x: (p.x - fittedRect.minX) / fittedRect.width, y: (p.y - fittedRect.minY) / fittedRect.height)
    }
}

#Preview("Page corner handles") {
    @Previewable @State var corners = PageCorners(points: [
        CGPoint(x: 0.1, y: 0.1), CGPoint(x: 0.9, y: 0.12), CGPoint(x: 0.88, y: 0.9), CGPoint(x: 0.12, y: 0.88),
    ])!
    PageCornerHandlesOverlay(fittedRect: CGRect(x: 20, y: 20, width: 300, height: 400), corners: $corners, onSquare: {})
        .frame(width: 340, height: 440)
}
