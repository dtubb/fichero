import SwiftUI

// MARK: - Navigator Mini-Map

/// A miniature navigation view showing the current viewport position within a larger image.
/// Displayed in the corner when zoomed in, allowing users to click/drag to pan the main view.
struct NavigatorMiniMap: View {
    // MARK: - Constants

    private enum Layout {
        static let cornerRadius: CGFloat = 6
        static let borderOpacity: Double = 0.3
        static let backgroundOpacity: Double = 0.7
        static let shadowRadius: CGFloat = 5
        static let shadowOffsetY: CGFloat = 2
        static let shadowOpacity: Double = 0.3
        static let hoverOpacity: Double = 1.0
        static let defaultOpacity: Double = 0.7
        static let hoverAnimationDuration: Double = 0.15
        static let minimumViewportSize: CGFloat = 8
        static let zoomThreshold: CGFloat = 0.99
    }

    private enum ViewportStyle {
        static let fillOpacity: Double = 0.15
        static let fillOpacityDragging: Double = 0.25
        static let strokeOpacity: Double = 1.0
        static let strokeOpacityDragging: Double = 0.8
        static let strokeWidth: CGFloat = 2
        static let strokeWidthDragging: CGFloat = 3
    }

    // MARK: - Properties

    let image: PlatformImage
    let visibleRect: CGRect  // Normalized 0-1 coordinates
    let onRectangleDragged: ((CGPoint) -> Void)?

    @State private var isHovering = false
    @State private var isDragging = false

    // MARK: - Computed Properties

    private var isZoomedIn: Bool {
        visibleRect.width < Layout.zoomThreshold || visibleRect.height < Layout.zoomThreshold
    }

    // MARK: - Body

    var body: some View {
        Image(platformImage: image)
            .resizable()
            .aspectRatio(contentMode: .fit)
            .background(Color.black.opacity(Layout.backgroundOpacity))
            .clipShape(RoundedRectangle(cornerRadius: Layout.cornerRadius))
            .overlay(
                RoundedRectangle(cornerRadius: Layout.cornerRadius)
                    .stroke(Color.white.opacity(Layout.borderOpacity), lineWidth: 1)
            )
            .shadow(
                color: .black.opacity(Layout.shadowOpacity),
                radius: Layout.shadowRadius,
                x: 0,
                y: Layout.shadowOffsetY
            )
            .overlay { gestureOverlay }
            .opacity(isHovering ? Layout.hoverOpacity : Layout.defaultOpacity)
            .onHover { hovering in
                withAnimation(.easeInOut(duration: Layout.hoverAnimationDuration)) {
                    isHovering = hovering
                }
            }
    }

    // MARK: - Subviews

    @ViewBuilder
    private var gestureOverlay: some View {
        GeometryReader { geometry in
            Color.clear
                .contentShape(Rectangle())
                .gesture(dragGesture(mapSize: geometry.size))

            if isZoomedIn {
                viewportIndicator(mapSize: geometry.size)
            }
        }
    }

    @ViewBuilder
    private func viewportIndicator(mapSize: CGSize) -> some View {
        let size = viewportSize(for: mapSize)
        let center = viewportCenter(for: mapSize)

        let fillOpacity = isDragging ? ViewportStyle.fillOpacityDragging : ViewportStyle.fillOpacity
        let strokeOpacity = isDragging ? ViewportStyle.strokeOpacityDragging : ViewportStyle.strokeOpacity
        let strokeWidth = isDragging ? ViewportStyle.strokeWidthDragging : ViewportStyle.strokeWidth

        RoundedRectangle(cornerRadius: 2)
            .fill(Color.accentColor.opacity(fillOpacity))
            .overlay(
                RoundedRectangle(cornerRadius: 2)
                    .stroke(Color.accentColor.opacity(strokeOpacity), lineWidth: strokeWidth)
            )
            .frame(width: size.width, height: size.height)
            .position(center)
            .allowsHitTesting(false)
    }

    // MARK: - Gestures

    private func dragGesture(mapSize: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { value in
                isDragging = true
                let newOrigin = normalizedOrigin(for: value.location, in: mapSize)
                onRectangleDragged?(newOrigin)
            }
            .onEnded { _ in
                isDragging = false
            }
    }

    // MARK: - Calculations

    private func viewportSize(for mapSize: CGSize) -> CGSize {
        CGSize(
            width: max(Layout.minimumViewportSize, visibleRect.width * mapSize.width),
            height: max(Layout.minimumViewportSize, visibleRect.height * mapSize.height)
        )
    }

    private func viewportCenter(for mapSize: CGSize) -> CGPoint {
        CGPoint(
            x: (visibleRect.origin.x + visibleRect.width / 2) * mapSize.width,
            y: (visibleRect.origin.y + visibleRect.height / 2) * mapSize.height
        )
    }

    private func normalizedOrigin(for location: CGPoint, in mapSize: CGSize) -> CGPoint {
        // Convert tap/drag location to normalized coordinates, centered on viewport
        let normalizedX = (location.x / mapSize.width) - (visibleRect.width / 2)
        let normalizedY = (location.y / mapSize.height) - (visibleRect.height / 2)

        // Clamp to valid range (keep viewport within bounds)
        return CGPoint(
            x: normalizedX.clamped(to: 0...(1 - visibleRect.width)),
            y: normalizedY.clamped(to: 0...(1 - visibleRect.height))
        )
    }
}

// MARK: - Comparable Extension

private extension Comparable {
    func clamped(to range: ClosedRange<Self>) -> Self {
        min(max(self, range.lowerBound), range.upperBound)
    }
}
