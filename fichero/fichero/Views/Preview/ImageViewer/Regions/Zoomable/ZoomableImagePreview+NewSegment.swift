#if os(macOS)
import SwiftUI

extension ZoomableImagePreview {
    /// A ⌥-dragged box (`source.editor.make-new-in-the-preview`): a segment of the kind last drawn, one `segment.create`
    /// and one ⌘Z, then selected and opened for text. A region is the box's outline; a line is a baseline across its middle.
    func drawBoxOfLastKind(_ box: [Double]) {
        guard box.count >= 4 else { return }
        if windowState?.lastDrawnKind == "line" {
            let middle = box[1] + box[3] / 2
            drawSegmentShape(.baseline, points: [[box[0], middle], [box[0] + box[2], middle]], selectingResult: true)
        } else {
            drawSegmentShape(.polygon, points: SegmentShapes.corners(ofRect: box), selectingResult: true)
        }
    }

    /// Select the segment just made and open it for text; the boxes were re-read before this runs.
    func selectNewSegment(_ id: String?, documentId: String) {
        guard let id, let scope = ocrGeometrySelectionScope, let boxes = ocrGeometry?.boxes,
              let index = boxes.firstIndex(where: { $0.segmentId == id }) else { return }
        regionSelection.select(index, artifactId: scope, documentId: documentId, in: boxes)
        windowState?.openForTextSegmentId = id
    }
}

#endif
