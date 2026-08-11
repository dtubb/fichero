import SwiftUI

enum DividerResizeAxis {
    case horizontal
    case vertical
}

/// Draggable divider for resizing adjacent panels.
/// - `leadingPanel`: the panel being resized is on the LEFT or TOP
///   (drag right/down to grow)
/// - `trailingPanel`: the panel being resized is on the RIGHT or BOTTOM
///   (drag left/up to grow)
struct ResizableDivider: View {
    @Binding var width: Double
    let minWidth: Double
    let maxWidth: Double
    var edge: Edge = .trailing
    var axis: DividerResizeAxis = .horizontal
    @State private var initialWidth: Double?

    enum Edge {
        case leading   // panel on left/top — drag right/down to grow
        case trailing  // panel on right/bottom — drag left/up to grow
    }

    /// True while a drag is in flight. The window-width observers gate on
    /// this (views audit B3): without it, a divider drag re-entered
    /// handleWindowWidthChange/updateColumnVisibility mid-drag and rewrote
    /// columnVisibility — invalidating the NavigationSplitView WHILE the
    /// user dragged, one of the width-change stall's feedback loops.
    var isDragging: Binding<Bool>?

    init(
        width: Binding<Double>,
        minWidth: Double,
        maxWidth: Double,
        edge: Edge = .trailing,
        axis: DividerResizeAxis = .horizontal,
        isDragging: Binding<Bool>? = nil
    ) {
        self._width = width
        self.minWidth = minWidth
        self.maxWidth = maxWidth
        self.edge = edge
        self.axis = axis
        self.isDragging = isDragging
    }

    var body: some View {
        // 8px clear hit zone with a 1px visible separator centered inside.
        Color.clear
            .frame(
                width: axis == .horizontal ? 8 : nil,
                height: axis == .vertical ? 8 : nil
            )
            .overlay(
                Rectangle()
                    .fill(Color(platformColor: .separatorColor))
                    .frame(
                        width: axis == .horizontal ? 1 : nil,
                        height: axis == .vertical ? 1 : nil
                    )
            )
            .contentShape(Rectangle())
            .onHover { hovering in
                #if os(macOS)
                if hovering {
                    (axis == .horizontal ? NSCursor.resizeLeftRight : NSCursor.resizeUpDown).set()
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
                        if initialWidth == nil {
                            initialWidth = width
                            isDragging?.wrappedValue = true
                        }
                        guard let start = initialWidth else { return }
                        let delta = axis == .horizontal
                            ? value.location.x - value.startLocation.x
                            : value.location.y - value.startLocation.y
                        let newWidth = edge == .trailing
                            ? start - delta
                            : start + delta
                        let clamped = min(max(newWidth, minWidth), maxWidth)
                        // Whole-point granularity: sub-point deltas recompose
                        // the entire content tree for an invisible change
                        // (views audit B1 — live-follow kept per Daniel's
                        // ruling; this halves-or-better the write rate for
                        // free without changing the feel).
                        if abs(clamped - width) >= 1 {
                            width = clamped
                        }
                    }
                    .onEnded { _ in
                        initialWidth = nil
                        isDragging?.wrappedValue = false
                    }
            )
    }
}

/// A border that briefly shows accent color when focus changes, then fades out quickly.
struct FadingFocusBorder: View {
    let isActive: Bool
    @State private var opacity: Double = 0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        RoundedRectangle(cornerRadius: 0)
            .strokeBorder(Color.accentColor, lineWidth: 2)
            .opacity(opacity)
            .onChange(of: isActive) { _, active in
                if active {
                    if reduceMotion {
                        opacity = 1.0
                        Task { @MainActor in
                            try? await Task.sleep(for: .milliseconds(400))
                            opacity = 0
                        }
                    } else {
                        withAnimation(.easeIn(duration: 0.1)) {
                            opacity = 1.0
                        }
                        Task { @MainActor in
                            try? await Task.sleep(for: .milliseconds(400))
                            withAnimation(.easeOut(duration: 0.3)) {
                                opacity = 0
                            }
                        }
                    }
                } else {
                    withAnimation(.easeOut(duration: 0.15)) {
                        opacity = 0
                    }
                }
            }
    }
}
