#if os(macOS)
import OSLog
import SwiftUI

/// Move, delete and Join on a page whose shown pass has NO artifact -- an imported page (#5152) --
/// through the audited segment actions (`SegmentEdit`), since the artifact regions route has no
/// artifact to address. Pages with an artifact keep the artifact path unchanged.
extension ZoomableImagePreview {
    /// The pass the shown boxes came from, when it has no artifact; nil sends the verb down the
    /// artifact path.
    var shownArtifactlessPassId: String? {
        guard ocrGeometryArtifactId == nil, let scope = ocrGeometrySelectionScope,
              scope.hasPrefix("pass:") else { return nil }
        return String(scope.dropFirst("pass:".count))
    }

    private var segmentEditStore: SegmentStore? {
        segmentService.map { SegmentStore.shared(for: $0) }
    }

    /// MOVE one box (by its index in the shown boxes) on an artifact-less pass. True when handled here.
    func moveSegment(index: Int, bbox: [Double]) -> Bool {
        guard let passId = shownArtifactlessPassId, let documentId, let store = segmentEditStore else { return false }
        guard let segment = store.segments(documentId: documentId)
            .first(where: { $0.passId == passId && $0.boxIndex == index }) else { return true }
        runSegmentEdit(SegmentEdit.move(segment, to: bbox), documentId: documentId, name: "Move Segment")
        return true
    }

    /// DELETE the selected boxes on an artifact-less pass. True when handled here.
    func deleteSelectedSegments() -> Bool {
        guard shownArtifactlessPassId != nil, let documentId else { return false }
        runSegmentEdit(SegmentEdit.delete(selectedSegments(documentId)), documentId: documentId, name: "Delete Segments")
        regionSelection.clear()
        return true
    }

    /// JOIN the selected boxes on an artifact-less pass. True when handled here.
    func joinSelectedSegments() -> Bool {
        guard shownArtifactlessPassId != nil, let documentId else { return false }
        runSegmentEdit(SegmentEdit.join(selectedSegments(documentId)), documentId: documentId, name: "Join Segments")
        regionSelection.clear()
        return true
    }

    /// The selection as segments, in the order picked, through the Inspector's one resolution.
    private func selectedSegments(_ documentId: String) -> [Segment] {
        guard let store = segmentEditStore else { return [] }
        let ids = InspectorPath.selectedSegmentIds(selection: regionSelection, documentId: documentId, store: store)
        let byId = Dictionary(
            store.segments(documentId: documentId).map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first }
        )
        return ids.compactMap { byId[$0] }
    }

    private func runSegmentEdit(
        _ planned: Result<SegmentEdit.Call, SegmentEdit.Refusal>, documentId: String, name: String
    ) {
        guard case .success(let call) = planned else {
            if case .failure(let refusal) = planned {
                Self.logger.notice("\(name, privacy: .public) not sent: \(String(describing: refusal), privacy: .public)")
            }
            return
        }
        guard let actionsService = actionStore?.actionsService, let store = segmentEditStore else { return }
        let runner = SegmentEditRunner(actionsService: actionsService, store: store)
        Task {
            do {
                try await runner.run(
                    call, documentId: documentId, actionName: name, undoManager: undoManager,
                    afterChange: { await loadOCRGeometry() }
                )
            } catch {
                Self.logger.error("\(name, privacy: .public) failed: \(String(describing: error), privacy: .public)")
            }
        }
    }
}
#endif
