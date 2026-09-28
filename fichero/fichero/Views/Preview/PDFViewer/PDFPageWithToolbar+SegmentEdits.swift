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
        let scope = pdfSelectionScope
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
            pageDocumentId: documentId
        )
        #else
        return PDFSegmentEditing()  // ponytail: no PDF overlay on iOS yet (#4418), so nothing to edit
        #endif
    }

    #if canImport(AppKit)
    /// The shown pass's selection scope (`SegmentDisplay.selectionScope`), nil when the boxes have no pass.
    var pdfSelectionScope: String? {
        guard let segmentService,
              let shown = SegmentDisplay.selected(for: effectiveGeometryDocumentId, store: SegmentStore.shared(for: segmentService))
        else { return nil }
        return SegmentDisplay.selectionScope(artifactId: shown.artifactId, passId: shown.passId)
    }

    /// The shown pass's segment at `index` reshaped: the image's rule, sent through `SegmentEditRunner`.
    func reshapePDFSegment(index: Int, _ target: SegmentShapes.Target, to points: [[Double]]) {
        guard let segmentService, let actionsService = pdfActionStore?.actionsService else { return }
        let store = SegmentStore.shared(for: segmentService)
        let documentId = effectiveGeometryDocumentId
        guard let shown = SegmentDisplay.selected(for: documentId, store: store),
              let segment = store.segments(documentId: documentId)
                .first(where: { $0.passId == shown.passId && $0.boxIndex == index }) else { return }
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
