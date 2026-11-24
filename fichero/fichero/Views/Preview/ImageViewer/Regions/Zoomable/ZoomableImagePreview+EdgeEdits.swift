#if os(macOS)
import OSLog
import SwiftUI

/// Edge edits on saved segments (`segment-editor.edges-drag-and-say-so`, `segment-editor.edges-move-by-key`): a resize
/// sends each box to its new rectangle (`SegmentEdit.move` scales the shapes with it), several boxes as one ⌘Z.
extension ZoomableImagePreview {
    /// Commit a drag's resize of one or several boxes. A lone box that is not a saved segment goes the old move path.
    func resizeSegments(_ changes: [(index: Int, bbox: [Double])]) {
        if refusesEditOnMappedRendition() { return }
        guard let documentId, let store = segmentEditStore else { return }
        let items = changes.compactMap { change in
            shownSegment(at: change.index, documentId, store).map { (segment: $0, bbox: change.bbox) }
        }
        guard items.count == changes.count, items.allSatisfy({ $0.segment.version != nil }) else {
            if changes.count == 1 { commitRegionMove(index: changes[0].index, bbox: changes[0].bbox) }
            return
        }
        sendResizes(items, documentId: documentId)
    }

    private func sendResizes(_ items: [(segment: Segment, bbox: [Double])], documentId: String) {
        if items.count == 1 {
            runSegmentEdit(SegmentEdit.move(items[0].segment, to: items[0].bbox), documentId: documentId, name: "Resize Segment")
            return
        }
        let plans = items.map { SegmentEdit.move($0.segment, to: $0.bbox) }
        guard let actionsService = actionStore?.actionsService else { return }
        Task {
            do {
                try await UndoableChange.batch(
                    plans, named: { "Resize \($0) Segments" }, service: actionsService, steps: windowSteps,
                    afterEach: { await loadOCRGeometry() },
                    change: { plan in
                        let call = try plan.get()
                        return [try await actionsService.invokeAction(name: call.action, params: call.params).auditId]
                    }
                )
            } catch {
                Self.logger.error("Resize Segments failed: \(String(describing: error), privacy: .public)")
                windowState?.segmentNotice = "Resize Segments failed: \(error.localizedDescription)"
            }
            await reloadSegmentsAfterRegionEdit()
        }
    }

    /// ⌥-arrow grows the selected boxes on the arrow's side, ⌃⌥-arrow shrinks them (1 px, 10 with ⇧). False when no saved
    /// segment is selected, so the arrow keeps its meaning; true once taken, even when the page's edge left nothing to send.
    func resizeSelectedByKey(side: EdgeKeys.Side, outward: Bool, fast: Bool) -> Bool {
        guard let documentId, imageSize.width > 0, imageSize.height > 0 else { return false }
        let segments = selectedSegments(documentId)
        guard !segments.isEmpty, segments.allSatisfy({ $0.version != nil && $0.anchor.rect != nil }) else { return false }
        if refusesEditOnMappedRendition() { return true }
        let old = segments.compactMap(\.anchor.rect)
        let new = EdgeKeys.plan(
            old, side: side, outward: outward, pixels: fast ? 10 : 1, imagePixels: [imageSize.width, imageSize.height]
        )
        let changed = zip(segments, zip(old, new)).filter { $0.1.0 != $0.1.1 }.map { (segment: $0.0, bbox: $0.1.1) }
        if !changed.isEmpty { sendResizes(changed, documentId: documentId) }
        return true
    }
}
#endif
