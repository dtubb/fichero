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

    func selectNewSegment(_ id: String?, documentId: String) {
        guard let id, let scope = ocrGeometrySelectionScope, let boxes = ocrGeometry?.boxes,
              let index = boxes.firstIndex(where: { $0.segmentId == id }) else { return }
        regionSelection.select(index, artifactId: scope, documentId: documentId, in: boxes)
        windowState?.openForTextSegmentId = id
    }
}

#endif
