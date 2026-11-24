import SwiftUI

#if os(macOS)  // RegionInteractionLayer is Mac-only (an AppKit event layer)

/// Reshape in Edit Segments: a press on a point of any of the ONE selected segment's shapes -- outline,
/// baseline, an extra area, path or point -- drags it; a press on a side's midpoint adds a point there
/// and drags it; ⌥-click removes a point (never below what the shape needs).
/// Committed through the host's `onReshapeCommit`, which sends `segment.update` with ⌘Z.
extension RegionInteractionLayer {
    /// The window's segment-editing mode (#5114). No window state reads as off.
    var isEditing: Bool { windowState?.isEditingSegments ?? false }

    /// The single selected box and its shapes, when it has any to reshape.
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
        if handleResize(event, in: size) { return true }
        switch event.phase {
        case .pressed:
            let began = event.clickCount == 1 && isEditing && beginReshape(at: event.point, option: event.option, in: size)
            // A press anywhere but a handle lets go of the point the arrow keys were nudging.
            if !began, windowState?.selectedShapePoint != nil { windowState?.selectedShapePoint = nil }
            return began
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
        switch ReshapeDrag.press(at: point, boxIndex: index, shapes: shapes, reach: reach, option: option) {
        case .none: return false
        case .refused: break  // ⌥ on a point the shape cannot spare: nothing is sent
        case .remove(let target, let fewer): onReshapeCommit?(index, target, fewer)
        case .drag(let drag): reshapeDrag = drag
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
        guard let drag = reshapeDrag else { return }
        // The point pressed is the one the arrow keys nudge next (1 px, ⇧ 10), dragged or not.
        windowState?.selectedShapePoint = SegmentShapes.PointRef(
            documentId: documentId, boxIndex: drag.boxIndex, target: drag.target, index: drag.pointIndex
        )
        guard drag.points != drag.original else { return }
        onReshapeCommit?(drag.boxIndex, drag.target, drag.points)
    }

    /// Resize by the edges and corners (#5215, `segment-editor.edges-drag-and-say-so`): a press within reach of any edge of the
    /// selected box -- or, with several selected, of their union -- grabs that edge (a corner, two), in any mode. The drag
    /// moves the same edge of every selected box by the same amount; the release is one commit (`onResizeCommit`, else
    /// `onMoveCommit` for one box). The edge is asked BEFORE a shape's point handles: a point lying on it yields to the frame.
    func handleResize(_ event: PreviewPointerEvent, in size: CGSize) -> Bool {
        let point = [Double(event.point.x), Double(event.point.y)]
        switch event.phase {
        case .pressed:
            guard event.clickCount == 1, !event.option, size.width > 0, size.height > 0,
                  let picked = selectedBoxIndices(), let union = Self.union(of: picked.map { allBoxes[$0].bbox }) else { return false }
            let reach = [Double(SelectionStyle.handleSide) / size.width * visible.width,
                         Double(SelectionStyle.handleSide) / size.height * visible.height]
            guard let handle = BoxResize.grab(at: point, of: union, reach: reach) else { return false }
            let boxes = picked.map { allBoxes[$0].bbox }
            resizeDrag = BoxResize.Drag(
                index: picked[0], handle: handle, bbox: boxes[0], start: point, indices: picked, origins: boxes, live: boxes
            )
            return true
        case .dragged:
            guard let drag = resizeDrag, drag.indices.allSatisfy(allBoxes.indices.contains) else { return false }
            resizeDragged(drag, to: point, shift: event.shift)
            return true
        case .released:
            guard let drag = resizeDrag else { return false }
            resizeDrag = nil
            guard drag.live != drag.origins, drag.indices.allSatisfy(allBoxes.indices.contains) else { return true }
            if let onResizeCommit {
                onResizeCommit(Array(zip(drag.indices, drag.live)).map { (index: $0, bbox: $1) })
            } else if drag.indices.count == 1 {
                onMoveCommit(drag.index, drag.live[0])
            }
            return true
        }
    }

    /// ⇧ fixes one axis by the drag's first direction (`segment-editor.expand-one-axis`); the boxes stay put until then.
    /// Letting go of ⇧ goes back to the free resize.
    private func resizeDragged(_ drag: BoxResize.Drag, to point: [Double], shift: Bool) {
        guard let union = Self.union(of: drag.origins) else { return }
        let place = BoxResize.position(of: drag.handle, on: union)
        var delta = [point[0] - place[0], point[1] - place[1]]
        resizeDrag?.axis = nil
        if shift {
            let axis = drag.axis ?? BoxResize.axis(from: drag.start, to: point)
            resizeDrag?.axis = axis
            switch axis {
            case .horizontal: delta[1] = 0
            case .vertical: delta[0] = 0
            case nil: delta = [0, 0]
            }
        }
        let live = BoxResize.resizedTogether(drag.origins, handle: drag.handle, by: delta)
        resizeDrag?.live = live
        resizeDrag?.bbox = live[0]
    }

    /// The selected boxes' positions in the full list (the first picked first), or nil when none are selected here.
    private func selectedBoxIndices() -> [Int]? {
        guard let artifactId, selection.artifactId == artifactId else { return nil }
        let picked = selection.resolvedIndices(in: allBoxes).filter(allBoxes.indices.contains)
        return picked.isEmpty ? nil : picked
    }

    /// The smallest rect holding every box in `boxes`.
    static func union(of boxes: [[Double]]) -> [Double]? {
        let valid = boxes.filter { $0.count >= 4 }
        guard !valid.isEmpty else { return nil }
        let minX = valid.map { $0[0] }.min() ?? 0, minY = valid.map { $0[1] }.min() ?? 0
        let maxX = valid.map { $0[0] + $0[2] }.max() ?? 0, maxY = valid.map { $0[1] + $0[3] }.max() ?? 0
        return [minX, minY, maxX - minX, maxY - minY]
    }

    /// The shape as it is being reshaped, over the drawn one until the edit lands.
    @ViewBuilder
    func liveReshape(in size: CGSize) -> some View {
        if let drag = resizeDrag {
            ForEach(Array(drag.live.enumerated()), id: \.offset) { _, bbox in
                if let rect = BoundingBoxGeometry.viewRect(normalized: bbox, in: size, visible: visible) {
                    Rectangle()
                        .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 1.5, dash: [4]))
                        .frame(width: rect.width, height: rect.height)
                        .offset(x: rect.minX, y: rect.minY)
                }
            }
        }
        if let drag = reshapeDrag {
            Path { path in
                let points = drag.points.compactMap { viewPoint($0, in: size) }
                guard let first = points.first else { return }
                path.move(to: first)
                points.dropFirst().forEach { path.addLine(to: $0) }
                if drag.target.isClosed { path.closeSubpath() }
            }
            .stroke(Color.accentColor, style: StrokeStyle(lineWidth: drag.target == .baseline ? 2 : 1.5, dash: [4]))
        }
    }

    private func viewPoint(_ normalized: [Double], in size: CGSize) -> CGPoint? {
        guard normalized.count >= 2, visible.width > 0, visible.height > 0 else { return nil }
        return CGPoint(x: (normalized[0] - visible.minX) / visible.width * size.width,
                       y: (normalized[1] - visible.minY) / visible.height * size.height)
    }
}
#endif
