import SwiftUI

/// A Reshape in progress (`source.editor.reshape`): which box, what is reshaped, the point being
/// dragged, and the points as they stand -- committed on release as one `segment.update`.
struct ReshapeDrag: Equatable {
    let boxIndex: Int
    let target: SegmentShapes.Target
    let pointIndex: Int
    var points: [[Double]]
    /// The points before the press, so a press that moves nothing sends nothing.
    let original: [[Double]]
}

/// Reshape in Edit Segments: a press on a point of the ONE selected segment's outline or baseline
/// drags it; a press on a side's midpoint adds a point there and drags it; ⌥-click removes a point.
/// Committed through the host's `onReshapeCommit`, which sends `segment.update` with ⌘Z.
extension RegionInteractionLayer {
    /// The single selected box and its shapes, when it has an outline or a baseline to reshape.
    private var reshapable: (index: Int, shapes: [SegmentShapes.Drawn])? {
        guard onReshapeCommit != nil, let artifactId, selection.artifactId == artifactId else { return nil }
        let picked = selection.resolvedIndices(in: allBoxes)
        guard picked.count == 1, let index = picked.first, allBoxes.indices.contains(index) else { return nil }
        let shapes = allBoxes[index].shapes
        return shapes.isEmpty ? nil : (index, shapes)
    }

    /// The pointer, for Reshape first: true when Reshape took the event (a press on a handle, or the
    /// drag and release of one it began), so nothing else acts on it.
    func handleReshape(_ event: PreviewPointerEvent, in size: CGSize) -> Bool {
        switch event.phase {
        case .pressed:
            return event.clickCount == 1 && isEditing && beginReshape(at: event.point, option: event.option, in: size)
        case .dragged:
            guard reshapeDrag != nil else { return false }
            dragReshape(to: event.point)
            return true
        case .released:
            guard reshapeDrag != nil else { return false }
            finishReshape()
            return true
        }
    }

    /// Mouse-down in Edit Segments. True when it began (or, with ⌥, finished) a Reshape.
    func beginReshape(at normalized: CGPoint, option: Bool, in size: CGSize) -> Bool {
        guard let found = reshapable, size.width > 0, size.height > 0 else { return false }
        let (index, shapes) = (found.index, found.shapes)
        // A handle's reach: its on-screen size, in page units at this zoom.
        let reach = [Double(SelectionStyle.handleSide) / size.width * visible.width,
                     Double(SelectionStyle.handleSide) / size.height * visible.height]
        let point = [Double(normalized.x), Double(normalized.y)]
        guard let handle = SegmentShapes.handle(at: point, in: shapes, tolerance: reach),
              let points = shapes.first(where: { Self.target(of: $0) == handle.target })?.points else { return false }
        switch handle {
        case .vertex(let target, let vertex) where option:
            // ⌥-click removes the point, unless the shape would have too few (then nothing is sent).
            if let fewer = SegmentShapes.removing(points, index: vertex, target) { onReshapeCommit?(index, target, fewer) }
        case .vertex(let target, let vertex):
            reshapeDrag = ReshapeDrag(boxIndex: index, target: target, pointIndex: vertex, points: points, original: points)
        case .side(let target, let after):
            let added = SegmentShapes.adding(points, after: after, at: point, target)
            reshapeDrag = ReshapeDrag(boxIndex: index, target: target, pointIndex: after + 1, points: added, original: points)
        }
        return true
    }

    func dragReshape(to normalized: CGPoint) {
        guard var drag = reshapeDrag else { return }
        drag.points = SegmentShapes.moving(drag.points, index: drag.pointIndex, to: [Double(normalized.x), Double(normalized.y)])
        reshapeDrag = drag
    }

    func finishReshape() {
        defer { reshapeDrag = nil }
        guard let drag = reshapeDrag, drag.points != drag.original else { return }
        onReshapeCommit?(drag.boxIndex, drag.target, drag.points)
    }

    /// The shape as it is being reshaped, over the drawn one until the edit lands.
    @ViewBuilder
    func liveReshape(in size: CGSize) -> some View {
        if let drag = reshapeDrag {
            Path { path in
                let points = drag.points.compactMap { viewPoint($0, in: size) }
                guard let first = points.first else { return }
                path.move(to: first)
                points.dropFirst().forEach { path.addLine(to: $0) }
                if drag.target == .polygon { path.closeSubpath() }
            }
            .stroke(Color.accentColor, style: StrokeStyle(lineWidth: drag.target == .baseline ? 2 : 1.5, dash: [4]))
        }
    }

    private func viewPoint(_ normalized: [Double], in size: CGSize) -> CGPoint? {
        guard normalized.count >= 2, visible.width > 0, visible.height > 0 else { return nil }
        return CGPoint(x: (normalized[0] - visible.minX) / visible.width * size.width,
                       y: (normalized[1] - visible.minY) / visible.height * size.height)
    }

    private static func target(of shape: SegmentShapes.Drawn) -> SegmentShapes.Target? {
        switch shape {
        case .polygon: .polygon
        case .baseline: .baseline
        case .path, .point: nil
        }
    }
}
