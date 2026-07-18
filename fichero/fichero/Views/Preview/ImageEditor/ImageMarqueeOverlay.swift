import SwiftUI

/// Rubber-band (marquee) region-select overlay drawn over a fitted image (#1265).
///
/// Reports the selection as a **normalized** rect (0…1 in image space) so the
/// caller can map it to source pixels regardless of the on-screen scale. The
/// overlay only handles the gesture + drawing; coordinate math lives here and
/// stays independent of the editor.
struct ImageMarqueeOverlay: View {
    /// The image's frame within the container, in container coordinates.
    let fittedRect: CGRect
    /// Selection in normalized image space (0…1). `nil` when there is no selection.
    @Binding var normalizedSelection: CGRect?

    /// Live drag rectangle in container coordinates (nil when not dragging).
    @State private var dragRect: CGRect?

    var body: some View {
        ZStack(alignment: .topLeading) {
            // Transparent hit area covering the whole canvas.
            Color.clear.contentShape(Rectangle())

            if let rect = displayRect {
                ZStack(alignment: .topLeading) {
                    Rectangle()
                        .fill(Color.accentColor.opacity(0.15))
                    Rectangle()
                        .strokeBorder(Color.accentColor, lineWidth: 1.5)
                }
                .frame(width: rect.width, height: rect.height)
                .offset(x: rect.minX, y: rect.minY)
                .allowsHitTesting(false)
            }
        }
        .contentShape(Rectangle())
        .gesture(
            DragGesture(minimumDistance: 3)
                .onChanged { value in
                    let start = clampToImage(value.startLocation)
                    let current = clampToImage(value.location)
                    dragRect = CGRect(
                        x: min(start.x, current.x),
                        y: min(start.y, current.y),
                        width: abs(current.x - start.x),
                        height: abs(current.y - start.y)
                    )
                }
                .onEnded { _ in
                    defer { dragRect = nil }
                    guard let rect = dragRect, rect.width > 4, rect.height > 4 else {
                        normalizedSelection = nil
                        return
                    }
                    normalizedSelection = normalize(rect)
                }
        )
    }

    /// Rect to draw: the live drag, or a previously committed selection.
    private var displayRect: CGRect? {
        if let dragRect { return dragRect }
        return normalizedSelection.map(denormalize)
    }

    /// Clamp a container-space point to the image's fitted rect.
    private func clampToImage(_ point: CGPoint) -> CGPoint {
        CGPoint(
            x: min(max(point.x, fittedRect.minX), fittedRect.maxX),
            y: min(max(point.y, fittedRect.minY), fittedRect.maxY)
        )
    }

    /// Container-space rect → normalized image-space rect (0…1).
    private func normalize(_ rect: CGRect) -> CGRect? {
        guard fittedRect.width > 0, fittedRect.height > 0 else { return nil }
        return CGRect(
            x: (rect.minX - fittedRect.minX) / fittedRect.width,
            y: (rect.minY - fittedRect.minY) / fittedRect.height,
            width: rect.width / fittedRect.width,
            height: rect.height / fittedRect.height
        )
    }

    /// Normalized image-space rect → container-space rect for drawing.
    private func denormalize(_ rect: CGRect) -> CGRect {
        CGRect(
            x: fittedRect.minX + rect.minX * fittedRect.width,
            y: fittedRect.minY + rect.minY * fittedRect.height,
            width: rect.width * fittedRect.width,
            height: rect.height * fittedRect.height
        )
    }
}

/// Geometry helper shared by the editor canvas: the rect an aspect-fit image
/// occupies inside a container of `containerSize`.
enum ImageFit {
    static func fittedRect(imagePixelSize: CGSize, in containerSize: CGSize) -> CGRect {
        guard imagePixelSize.width > 0, imagePixelSize.height > 0,
              containerSize.width > 0, containerSize.height > 0 else {
            return .zero
        }
        let scale = min(
            containerSize.width / imagePixelSize.width,
            containerSize.height / imagePixelSize.height
        )
        let width = imagePixelSize.width * scale
        let height = imagePixelSize.height * scale
        return CGRect(
            x: (containerSize.width - width) / 2,
            y: (containerSize.height - height) / 2,
            width: width,
            height: height
        )
    }
}
