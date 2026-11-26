#if os(macOS)
import SwiftUI

extension ZoomableImagePreview {
    /// A ⌥-dragged box (`source.editor.make-new-in-the-preview`): a segment of the kind last drawn (a line gets a
    /// baseline across the middle), one `segment.create`, selected and opened for text.
    func drawBoxOfLastKind(_ box: [Double]) {
        guard box.count >= 4 else { return }
        if windowState?.lastDrawnKind == "line" {
            let middle = box[1] + box[3] / 2
            drawSegmentShape(.baseline, points: [[box[0], middle], [box[0] + box[2], middle]], selectingResult: true)
        } else {
            drawSegmentShape(.polygon, points: SegmentShapes.corners(ofRect: box), selectingResult: true)
        }
    }

    /// PAINT a line (`segment-editor.paintbrush`): one `segment.create` with the brush's stroke, in the region holding most
    /// of it; the engine makes the outline and the baseline. ⌘Z.
    func drawPaintStroke(_ stroke: [[Double]], widthPixels: Double) {
        if refusesEditOnMappedRendition() { return }
        guard let store = segmentEditStore else { return }
        let onThePass = documentId.map { id in store.segments(documentId: id).filter { $0.passId == ocrGeometryPassId } } ?? []
        switch StrokeTarget.resolve(
            documentId: documentId, passId: ocrGeometryPassId, onPass: onThePass,
            region: SegmentShapes.containingRegion(for: stroke, among: onThePass)
        ) {
        case .failure(let refusal):
            Self.logger.notice("Paintbrush stroke not sent: \(refusal.words, privacy: .public)")
            windowState?.segmentNotice = refusal.words
        case .success(let target):
            runSegmentEdit(
                PaintbrushStroke.create(stroke, widthPixels: widthPixels, on: target),
                documentId: target.documentId, name: "Paint Line"
            )
            windowState?.lastDrawnKind = "line"
        }
    }

    func selectNewSegment(_ id: String?, documentId: String, openForText: Bool = true) {
        guard let id, let scope = ocrGeometrySelectionScope, let boxes = ocrGeometry?.boxes,
              let index = boxes.firstIndex(where: { $0.segmentId == id }) else { return }
        regionSelection.select(index, artifactId: scope, documentId: documentId, in: boxes)
        if openForText { windowState?.openForTextSegmentId = id }
    }

    /// After each re-read of a Join (it, its undo, its redo): the kept line is selected, or the joined lines once undone.
    func selectAfterJoin(_ joined: [String], documentId: String) {
        guard let store = segmentEditStore else { return }
        let live = Set(store.segments(documentId: documentId).map(\.id))
        InspectorPath.select(
            segmentIds: SegmentEdit.selectionAfterJoin(joined: joined, live: live),
            into: regionSelection, documentId: documentId, store: store
        )
    }
}

#endif
