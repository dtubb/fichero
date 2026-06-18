import SwiftUI

/// Draggable divider for resizing adjacent panels.
/// - `leadingPanel`: the panel being resized is on the LEFT (drag right to grow)
/// - `trailingPanel`: the panel being resized is on the RIGHT (drag left to grow)
struct ResizableDivider: View {
    @Binding var width: Double
    let minWidth: Double
    let maxWidth: Double
    var edge: Edge = .trailing
    @State private var initialWidth: Double?

    enum Edge {
        case leading   // panel on left — drag right to grow
        case trailing  // panel on right — drag left to grow
    }

    var body: some View {
        // 8px clear hit zone with a 1px visible separator centered inside.
        Color.clear
            .frame(width: 8)
            .overlay(
                Rectangle()
                    .fill(Color(platformColor: .separatorColor))
                    .frame(width: 1)
            )
            .contentShape(Rectangle())
            .onHover { hovering in
                #if os(macOS)
                if hovering {
                    NSCursor.resizeLeftRight.set()
                } else {
                    NSCursor.arrow.set()
                }
                #endif
            }
            .gesture(
                // Use global coordinate space so the delta is stable even when
                // the divider moves during drag (the classic SwiftUI oscillation bug).
                DragGesture(minimumDistance: 1, coordinateSpace: .global)
                    .onChanged { value in
                        if initialWidth == nil { initialWidth = width }
                        guard let start = initialWidth else { return }
                        let delta = value.location.x - value.startLocation.x
                        let newWidth = edge == .trailing
                            ? start - delta
                            : start + delta
                        width = min(max(newWidth, minWidth), maxWidth)
                    }
                    .onEnded { _ in
                        initialWidth = nil
                    }
            )
    }
}

/// A border that briefly shows accent color when focus changes, then fades out.
struct FadingFocusBorder: View {
    let isActive: Bool
    @State private var opacity: Double = 0

    var body: some View {
        RoundedRectangle(cornerRadius: 0)
            .strokeBorder(Color.accentColor, lineWidth: 2)
            .opacity(opacity)
            .onChange(of: isActive) { _, active in
                if active {
                    withAnimation(.easeIn(duration: 0.15)) {
                        opacity = 1.0
                    }
                    Task { @MainActor in
                        try? await Task.sleep(for: .seconds(2))
                        withAnimation(.easeOut(duration: 0.8)) {
                            opacity = 0
                        }
                    }
                } else {
                    withAnimation(.easeOut(duration: 0.2)) {
                        opacity = 0
                    }
                }
            }
    }
}
