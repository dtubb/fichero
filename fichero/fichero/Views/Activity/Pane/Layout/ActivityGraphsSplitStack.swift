import SwiftUI

/// The Activity window's centre: the rows (or the recipes) over the graphs, the divider the person drags
/// (`activity.window.graph-on-every-view`, `activity.graphs.own-pane`, decisions 34, 41).
///
/// Drawn in SwiftUI, never as a `VSplitView` (#6661): an AppKit split view inside the window's `NavigationSplitView`,
/// beside the Inspector, re-reported its panes' sizes on every constraints pass once the centre was narrow, and the
/// window ended the app ("more Update Constraints in Window passes than there are views in the window"). Here no pane
/// reports a size to anything: the graphs' height is the person's drag alone, kept per window, and is only clamped
/// when drawn so both panes keep their minimums. Nothing is written from layout.
struct ActivityGraphsSplitStack<Rows: View, Graphs: View>: View {
    @ViewBuilder var rows: Rows
    @ViewBuilder var graphs: Graphs

    /// The graphs' height as the person left it (kept per window, so Full Size and back gives the height it had).
    @SceneStorage("activity.graphs.height") private var graphsHeight = Self.defaultGraphsHeight
    /// How far the divider has moved in the drag under way, in whole points (down is positive). Gesture state: a drag
    /// that is cancelled rather than ended (the window loses focus, a sheet opens) puts the divider back, and the
    /// height is kept only when the drag ends.
    @GestureState private var dragOffset: Double = 0

    nonisolated static var defaultGraphsHeight: Double { 180 }
    nonisolated static var rowsMinHeight: Double { 140 }
    nonisolated static var graphsMinHeight: Double { 120 }
    /// The divider's own strip, the line centred in it: it takes the drag without lying over either pane.
    nonisolated static var dividerHeight: Double { 8 }
    /// What one VoiceOver or keyboard adjustment moves the divider.
    nonisolated static var adjustmentStep: Double { 40 }

    var body: some View {
        GeometryReader { proxy in
            let total = Double(proxy.size.height)
            VStack(spacing: 0) {
                rows
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                divider(total: total)
                graphs
                    .frame(maxWidth: .infinity)
                    .frame(height: Self.clamped(Self.clamped(graphsHeight, total: total) - dragOffset, total: total))
            }
        }
    }

    private func divider(total: Double) -> some View {
        Color.clear
            .frame(maxWidth: .infinity)
            .frame(height: Self.dividerHeight)
            .overlay { Divider() }
            .contentShape(Rectangle())
            #if os(macOS)
            .pointerStyle(.rowResize)
            #endif
            .gesture(
                // The global space keeps the delta steady while the divider moves under the pointer.
                DragGesture(minimumDistance: 1, coordinateSpace: .global)
                    // Whole points only: a sub-point move would lay the table and the chart out again for nothing.
                    .updating($dragOffset) { drag, offset, _ in offset = Double(drag.translation.height).rounded() }
                    .onEnded { drag in
                        let start = Self.clamped(graphsHeight, total: total)
                        graphsHeight = Self.clamped(start - Double(drag.translation.height).rounded(), total: total)
                    }
            )
            // The splitter VSplitView gave VoiceOver and the keyboard: adjustable, an increment makes the graphs taller.
            .accessibilityElement()
            .accessibilityLabel("Graphs height")
            .accessibilityValue("\(Int(Self.clamped(graphsHeight, total: total))) points")
            .accessibilityAdjustableAction { direction in
                let step = direction == .increment ? Self.adjustmentStep : -Self.adjustmentStep
                graphsHeight = Self.clamped(Self.clamped(graphsHeight, total: total) + step, total: total)
            }
            .accessibilityIdentifier("activity.graphs.divider")
    }

    /// The graphs' height drawn in a centre `total` tall: the wanted height, kept between the graphs' minimum and the
    /// height that leaves the rows theirs; in a centre too short for both, the graphs keep their minimum.
    nonisolated static func clamped(_ wanted: Double, total: Double) -> Double {
        let most = max(graphsMinHeight, total - rowsMinHeight - dividerHeight)
        guard wanted.isFinite else { return min(defaultGraphsHeight, most) }
        return min(max(wanted, graphsMinHeight), most)
    }
}

#Preview("Rows over graphs") {
    ActivityGraphsSplitStack {
        Color.blue.opacity(0.15).overlay { Text("Rows") }
    } graphs: {
        Color.green.opacity(0.15).overlay { Text("Graphs") }
    }
    .frame(width: 600, height: 480)
}
