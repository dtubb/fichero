import SwiftUI

#if os(macOS)  // RegionInteractionLayer is Mac-only (an AppKit event layer)

/// The Knife in Edit Segments (`segment-editor.split-knife`): with K held, or the Knife chosen in the tool row, a drag
/// draws a stroke, and letting go
/// hands it to the host (`onKnifeCommit`), which sends it once as `segment.split` with `cut_path`. A stroke too
/// short to cross anything is dropped. Nothing is cut while the stroke is drawn.
extension RegionInteractionLayer {
    /// True when the event belongs to a knife stroke (so nothing else acts on it).
    func handleKnife(_ event: PreviewPointerEvent) -> Bool {
        guard let windowState, onKnifeCommit != nil, drawsSegments else { return false }
        guard windowState.knifeHeld || windowState.knifeArmed || !windowState.knifeStroke.isEmpty else { return false }
        let point = [Double(event.point.x), Double(event.point.y)]
        switch event.phase {
        case .pressed:
            windowState.knifeStroke = [point]
        case .dragged:
            guard !windowState.knifeStroke.isEmpty else { return true }
            windowState.knifeStroke.append(point)
        case .released:
            let stroke = KnifeStroke.thinned(windowState.knifeStroke + [point])
            windowState.knifeStroke = []
            if windowState.knifeHeld { windowState.knifeStrokedWhileHeld = true }
            if stroke.count >= 2 { onKnifeCommit?(stroke) }
        }
        return true
    }

    /// The segment editor's word about the edit just made, over the top of the page; it clears itself.
    @ViewBuilder
    func segmentNotice() -> some View {
        if let notice = windowState?.segmentNotice {
            Text(notice)
                .font(.callout)
                .padding(.horizontal, 10).padding(.vertical, 4)
                .background(.regularMaterial, in: Capsule())
                .frame(maxWidth: .infinity, alignment: .top)
                .padding(.top, 8)
                .accessibilityIdentifier("segmentEditor.notice")
                .task(id: notice) {
                    try? await Task.sleep(for: .seconds(5))
                    if windowState?.segmentNotice == notice { windowState?.segmentNotice = nil }
                }
        }
    }

    /// What the Simplify slider would make of the selection (`segment-editor.vertices`), drawn over the page while held.
    @ViewBuilder
    func liveSimplify(in size: CGSize) -> some View {
        let paths = windowState?.simplifyPreview ?? []
        if !paths.isEmpty, visible.width > 0, visible.height > 0 {
            Path { path in
                for points in paths where points.count >= 2 {
                    path.addLines(points.map {
                        CGPoint(x: ($0[0] - visible.minX) / visible.width * size.width,
                                y: ($0[1] - visible.minY) / visible.height * size.height)
                    })
                }
            }
            .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 1.5, lineJoin: .round, dash: [4, 3]))
        }
    }

    /// The stroke so far, drawn over the page.
    @ViewBuilder
    func liveKnife(in size: CGSize) -> some View {
        let stroke = windowState?.knifeStroke ?? []
        if stroke.count >= 2, visible.width > 0, visible.height > 0 {
            Path { path in
                let points = stroke.map {
                    CGPoint(x: ($0[0] - visible.minX) / visible.width * size.width,
                            y: ($0[1] - visible.minY) / visible.height * size.height)
                }
                path.addLines(points)
            }
            .stroke(Color.red, style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
        }
    }
}

#endif

/// The Knife's stroke, made ready to send, and the key that holds it.
enum KnifeStroke {
    /// What K does to the held Knife: down with no modifier in Edit Segments holds it, up lets it go (whatever else
    /// changed meanwhile); nil when the key is not the Knife's.
    static func held(pressed: Bool, modifiers: EventModifiers, isEditing: Bool, wasHeld: Bool) -> Bool? {
        if !pressed { return wasHeld ? false : nil }
        guard isEditing, modifiers.subtracting(.capsLock).isEmpty else { return nil }
        return true
    }

    /// The stroke without points closer than `spacing` (page fractions) to the one before, so a slow drag does not
    /// send a point per pixel; the last point is always kept, so the stroke ends where it was let go.
    static func thinned(_ points: [[Double]], spacing: Double = 0.002) -> [[Double]] {
        guard let first = points.first, let last = points.last, points.count > 2 else { return points }
        var kept = [first]
        for point in points.dropFirst().dropLast() where point.count >= 2 {
            if let previous = kept.last, hypot(point[0] - previous[0], point[1] - previous[1]) >= spacing {
                kept.append(point)
            }
        }
        if let previous = kept.last, previous != last { kept.append(last) }
        return kept.count >= 2 ? kept : [first, last]
    }
}
