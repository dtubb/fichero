import SwiftUI

/// Reshape in Edit Segments: a press on a point of any of the ONE selected segment's shapes -- outline,
/// baseline, an extra area, path or point -- drags it; a press on a side's midpoint adds a point there
/// and drags it; ⌥-click removes a point (never below what the shape needs).
/// Committed through the host's `onReshapeCommit`, which sends `segment.update` with ⌘Z.
extension RegionInteractionLayer {
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

    /// Resize by the eight handles (#5215): a press on one of the ONE selected box's handles in Edit
    /// Segments drags that corner or edge; the release is one move to the new box (`onMoveCommit`, which
    /// sends `segment.update` with the version read and ⌘Z, the shapes scaled with it). Asked BEFORE a
    /// shape's point handles: a point lying exactly on a frame handle yields to the frame.
    func handleResize(_ event: PreviewPointerEvent, in size: CGSize) -> Bool {
        let point = [Double(event.point.x), Double(event.point.y)]
        switch event.phase {
        case .pressed:
            guard event.clickCount == 1, isEditing, !event.option, size.width > 0, size.height > 0,
                  let index = singleSelectedIndex else { return false }
            let bbox = allBoxes[index].bbox
            let reach = [Double(SelectionStyle.handleSide) / size.width * visible.width,
                         Double(SelectionStyle.handleSide) / size.height * visible.height]
            guard let handle = BoxResize.handle(at: point, of: bbox, reach: reach) else { return false }
            resizeDrag = BoxResize.Drag(index: index, handle: handle, bbox: bbox)
            return true
        case .dragged:
            guard let drag = resizeDrag, allBoxes.indices.contains(drag.index) else { return false }
            resizeDrag?.bbox = BoxResize.resized(allBoxes[drag.index].bbox, handle: drag.handle, to: point)
            return true
        case .released:
            guard let drag = resizeDrag else { return false }
            resizeDrag = nil
            if allBoxes.indices.contains(drag.index), drag.bbox != allBoxes[drag.index].bbox {
                onMoveCommit(drag.index, drag.bbox)
            }
            return true
        }
    }

    /// The one selected box, by its position in the full list.
    private var singleSelectedIndex: Int? {
        guard let artifactId, selection.artifactId == artifactId else { return nil }
        let picked = selection.resolvedIndices(in: allBoxes)
        guard picked.count == 1, let index = picked.first, allBoxes.indices.contains(index) else { return nil }
        return index
    }

    /// The shape as it is being reshaped, over the drawn one until the edit lands.
    @ViewBuilder
    func liveReshape(in size: CGSize) -> some View {
        if let drag = resizeDrag, let rect = BoundingBoxGeometry.viewRect(normalized: drag.bbox, in: size, visible: visible) {
            Rectangle()
                .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 1.5, dash: [4]))
                .frame(width: rect.width, height: rect.height)
                .offset(x: rect.minX, y: rect.minY)
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
