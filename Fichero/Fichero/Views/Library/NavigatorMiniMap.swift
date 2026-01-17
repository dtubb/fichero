import SwiftUI

// MARK: - Navigator Mini-Map (top right corner)

struct NavigatorMiniMap: View {
    let image: NSImage
    let cursorPosition: CGPoint
    let visibleRect: CGRect  // Normalized 0-1 coordinates
    var onRectangleDragged: ((CGPoint) -> Void)?  // Called with new normalized center position

    @State private var isHovering = false
    @State private var isDraggingRect = false

    var body: some View {
        ZStack(alignment: .topTrailing) {
            // Thumbnail image
            Image(nsImage: image)
                .resizable()
                .aspectRatio(contentMode: .fit)

            // Visible area rectangle overlay
            GeometryReader { geometry in
                visibleRectOverlay(mapSize: geometry.size)
            }
        }
        .background(Color.black.opacity(0.7))
        .cornerRadius(6)
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(Color.white.opacity(0.3), lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.3), radius: 5, x: 0, y: 2)
        .opacity(isHovering ? 1.0 : 0.7)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.15)) {
                isHovering = hovering
            }
        }
    }

    /// Calculate and draw the visible rect overlay
    @ViewBuilder
    private func visibleRectOverlay(mapSize: CGSize) -> some View {
        // Calculate actual image bounds within the map (accounting for aspect ratio)
        let imageAspect = image.size.width / image.size.height
        let mapAspect = mapSize.width / mapSize.height

        let imageRect = imageAspect > mapAspect
            ? CGRect(x: 0,
                     y: (mapSize.height - mapSize.width / imageAspect) / 2,
                     width: mapSize.width,
                     height: mapSize.width / imageAspect)
            : CGRect(x: (mapSize.width - mapSize.height * imageAspect) / 2,
                     y: 0,
                     width: mapSize.height * imageAspect,
                     height: mapSize.height)

        // Draw visible area indicator (when zoomed in)
        if visibleRect.width < 0.99 || visibleRect.height < 0.99 {
            let rectWidth = max(8, visibleRect.width * imageRect.width)
            let rectHeight = max(8, visibleRect.height * imageRect.height)
            // Position the center of the rectangle (position() centers the view at the given point)
            let rectCenterX = imageRect.origin.x + (visibleRect.origin.x + visibleRect.width / 2) * imageRect.width
            let rectCenterY = imageRect.origin.y + (visibleRect.origin.y + visibleRect.height / 2) * imageRect.height

            ZStack {
                // Fill background
                Rectangle()
                    .fill(Color.accentColor.opacity(isDraggingRect ? 0.25 : 0.15))
                // Stroke border
                Rectangle()
                    .stroke(
                        isDraggingRect ? Color.accentColor.opacity(0.8) : Color.accentColor,
                        lineWidth: isDraggingRect ? 3 : 2
                    )
            }
            .frame(width: rectWidth, height: rectHeight)
            .position(x: rectCenterX, y: rectCenterY)
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { value in
                        isDraggingRect = true
                        // Convert drag location to normalized image coordinates
                        let dragX = value.location.x
                        let dragY = value.location.y

                        // Calculate normalized position (centered on drag point)
                        var normalizedX = (dragX - imageRect.origin.x) / imageRect.width - visibleRect.width / 2
                        var normalizedY = (dragY - imageRect.origin.y) / imageRect.height - visibleRect.height / 2

                        // Clamp to valid range (account for rect size)
                        normalizedX = max(0, min(1 - visibleRect.width, normalizedX))
                        normalizedY = max(0, min(1 - visibleRect.height, normalizedY))

                        onRectangleDragged?(CGPoint(x: normalizedX, y: normalizedY))
                    }
                    .onEnded { _ in
                        isDraggingRect = false
                    }
            )
            .onHover { hovering in
                if hovering {
                    NSCursor.openHand.push()
                } else {
                    NSCursor.pop()
                }
            }
        }
    }
}
