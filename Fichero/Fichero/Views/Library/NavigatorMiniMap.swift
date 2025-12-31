import SwiftUI

// MARK: - Navigator Mini-Map (top right corner)

struct NavigatorMiniMap: View {
    let image: NSImage
    let cursorPosition: CGPoint
    let visibleRect: CGRect  // Normalized 0-1 coordinates

    @State private var isHovering = false

    var body: some View {
        ZStack(alignment: .topLeading) {
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
            let rectX = imageRect.origin.x + visibleRect.origin.x * imageRect.width + rectWidth / 2
            let rectY = imageRect.origin.y + visibleRect.origin.y * imageRect.height + rectHeight / 2

            Rectangle()
                .stroke(Color.accentColor, lineWidth: 2)
                .background(Color.accentColor.opacity(0.15))
                .frame(width: rectWidth, height: rectHeight)
                .position(x: rectX, y: rectY)
        }
    }
}
