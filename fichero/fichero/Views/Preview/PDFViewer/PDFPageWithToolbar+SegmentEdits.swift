import OSLog
import SwiftUI

private let pdfSegmentEditLogger = Logger(subsystem: "app.fichero.fichero", category: "PDFSegmentEdits")

/// Reshape on a PDF page (`source.editor.reshape`): in Edit Segments a click selects a segment, and its
/// handles drag, add and remove points -- the same `SegmentShapes.reshape` the image overlay sends, one
/// `segment.update` checked against the version read, ⌘Z by its audit id.
extension PDFPageWithToolbar {
    var pdfSegmentEditing: PDFSegmentEditing {
        #if canImport(AppKit)
        let boxes = ocrGeometry?.boxes ?? []
        let documentId = effectiveGeometryDocumentId
        let scope = pdfGeometryScope
        let selection = pdfRegionSelection
        let windowState = pdfWindowState
        return PDFSegmentEditing(
            isEditing: pdfWindowState?.isEditingSegments == true,
            selected: PDFSegmentEditing.selected(from: selection, among: boxes, scope: scope, documentId: documentId),
            select: { box in
                PDFSegmentEditing.select(box, among: boxes, scope: scope, documentId: documentId, into: selection)
                windowState?.focusRegionSelection(selection)
            },
            commit: { index, target, points in reshapePDFSegment(index: index, target, to: points) },
            pageDocumentId: documentId,
            openPopover: { popover in pdfSegmentPopover = popover }
        )
        #else
        return PDFSegmentEditing()  // ponytail: no PDF overlay on iOS yet (#4418), so nothing to edit
        #endif
    }

    #if canImport(AppKit)
    /// The drawn box at `index` reshaped: the image's rule, sent through `SegmentEditRunner`. The segment is
    /// the one the box on screen draws (`OCRGeometryBox.segmentId`, set by `loadOCRGeometry` from the one
    /// `SegmentDisplay.selected`), never a second answer to which pass is shown (#5467).
    func reshapePDFSegment(index: Int, _ target: SegmentShapes.Target, to points: [[Double]]) {
        guard let segmentService, let actionsService = pdfActionStore?.actionsService else { return }
        let store = SegmentStore.shared(for: segmentService)
        let documentId = effectiveGeometryDocumentId
        guard let boxes = ocrGeometry?.boxes, boxes.indices.contains(index), let segmentId = boxes[index].segmentId,
              let segment = store.segments(documentId: documentId).first(where: { $0.id == segmentId }) else { return }
        let name = target == .polygon ? "Reshape Segment" : "Reshape Baseline"
        guard case .success(let call) = SegmentShapes.reshape(segment, target, to: points) else {
            pdfSegmentEditLogger.notice("\(name, privacy: .public) not sent: refused")
            return
        }
        let undoManager = pdfUndoManager
        Task {
            do {
                try await SegmentEditRunner(actionsService: actionsService, store: store).run(
                    call, documentId: documentId, actionName: name, undoManager: undoManager,
                    afterChange: { await loadOCRGeometry() }
                )
            } catch {
                pdfSegmentEditLogger.error("\(name, privacy: .public) failed: \(String(describing: error), privacy: .public)")
            }
        }
    }
    #endif
}
