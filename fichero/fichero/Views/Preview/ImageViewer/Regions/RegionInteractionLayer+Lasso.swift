import SwiftUI

#if os(macOS)  // RegionInteractionLayer is Mac-only (an AppKit event layer)

/// The lasso in Select (`segment-editor.select-marquee-lasso`): ⌥-drag from empty page draws a loop, and letting go
/// selects every segment mostly inside it, at the level being edited (lines; regions with ⌘), ⇧ adding to the selection.
/// Selecting is not an action: nothing is sent.
extension RegionInteractionLayer {
    /// True when the event belongs to a lasso (so nothing else acts on it).
    func handleLasso(_ event: PreviewPointerEvent, at viewPoint: CGPoint, in size: CGSize) -> Bool {
        let point = [Double(event.point.x), Double(event.point.y)]
        switch event.phase {
        case .pressed:
            guard event.option, event.clickCount == 1, isBandSelecting, artifactId != nil,
                  !hitsAnything(at: viewPoint, in: size) else { return false }
            lasso = [point]
            bandCommand = event.command
            return true
        case .dragged:
            guard !lasso.isEmpty else { return false }
            lasso.append(point)
            return true
        case .released:
            guard !lasso.isEmpty else { return false }
            let loop = KnifeStroke.thinned(lasso + [point])
            lasso = []
            if loop.count >= 3 { selectRegions(inLoop: loop) } else { handleTap(at: viewPoint, in: size) }
            return true
        }
    }

    /// The loop so far, drawn over the page.
    @ViewBuilder
    func liveLasso(in size: CGSize) -> some View {
        if lasso.count >= 2, visible.width > 0, visible.height > 0 {
            Path { path in
                path.addLines(lasso.map {
                    CGPoint(x: ($0[0] - visible.minX) / visible.width * size.width,
                            y: ($0[1] - visible.minY) / visible.height * size.height)
                })
            }
            .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 1, lineJoin: .round, dash: [4, 3]))
            .accessibilityIdentifier("segmentEditor.lasso")
        }
    }
}

#endif
