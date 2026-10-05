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

    /// RESHAPE one box's outline or baseline (by its index in the shown boxes): `segment.update`, checked
    /// against the version read, ⌘Z. A segment's shapes are on a segment pass, so this is the only path.
    /// On a page whose boxes are still its result's (no version to check against, #5235) the page is
    /// converted first -- `segment.convert_and_edit`, its own ⌘Z -- and the reshape goes to the segment it
    /// became. Before this the drag snapped back with nothing sent and nothing said.
    func reshapeSegment(index: Int, _ target: SegmentShapes.Target, to points: [[Double]]) {
        let name = target == .polygon ? "Reshape Segment" : "Reshape Baseline"
        guard let documentId, let store = segmentEditStore, let segment = shownSegment(at: index, documentId, store) else {
            Self.logger.notice("\(name, privacy: .public) not sent: box \(index) is not a segment on the shown pass")
            return
        }
        guard segment.version == nil else {
            runSegmentEdit(SegmentShapes.reshape(segment, target, to: points), documentId: documentId, name: name)
            return
        }
        guard let actionsService = actionStore?.actionsService else { return }
        Task {
            do {
                try await AuditedAction.run(
                    "segment.convert_and_edit", params: ConvertPageRequest(documentId: documentId),
                    actionName: "Convert Page", actionsService: actionsService, undoManager: undoManager,
                    afterChange: { await reloadSegmentsAfterRegionEdit() }
                )
                await reloadSegmentsAfterRegionEdit()
                guard let converted = shownSegment(at: index, documentId, store), converted.version != nil else {
                    Self.logger.error("\(name, privacy: .public) not sent: box \(index) has no segment after converting")
                    return
                }
                runSegmentEdit(SegmentShapes.reshape(converted, target, to: points), documentId: documentId, name: name)
            } catch {
                Self.logger.error("\(name, privacy: .public) failed converting the page: \(String(describing: error), privacy: .public)")
            }
        }
    }

    /// The segment drawn as box `index`: the one the box on screen names (`OCRGeometryBox.segmentId`, from
    /// the one `SegmentDisplay.selected` the overlay loaded), never the shown pass asked for again (#5467).
    private func shownSegment(at index: Int, _ documentId: String, _ store: SegmentStore) -> Segment? {
        guard let boxes = ocrGeometry?.boxes, boxes.indices.contains(index), let segmentId = boxes[index].segmentId
        else { return nil }
        return store.segments(documentId: documentId).first { $0.id == segmentId }
    }

    /// The Segments store re-read, then the boxes redrawn from it (#5235): the overlay draws from the store,
    /// so after an edit through the artifact route -- or its ⌘Z -- a stale store painted the old boxes back.
    func reloadSegmentsAfterRegionEdit() async {
        guard let documentId, let store = segmentEditStore else { return }
        await store.load(documentId: documentId, force: true)
        await loadOCRGeometry()
    }

    /// NUDGE the shape point last pressed (an arrow key in Edit Segments): 1 image pixel, 10 with ⇧, as one
    /// `segment.update` with ⌘Z. False when no point is selected here, so the arrow keeps its paging.
    /// ponytail: one audited edit per key press; coalesce a held key into one if the audit trail grows.
    func nudgeSelectedShapePoint(_ deltaX: Double, _ deltaY: Double, fast: Bool) -> Bool {
        guard windowState?.isEditingSegments == true, let ref = windowState?.selectedShapePoint,
              let documentId, ref.documentId == documentId,
              let store = segmentEditStore, imageSize.width > 0, imageSize.height > 0,
              let segment = shownSegment(at: ref.boxIndex, documentId, store),
              let points = SegmentShapes.points(of: segment, ref.target) else { return false }
        let step = fast ? 10.0 : 1.0
        let moved = SegmentShapes.nudging(
            points, index: ref.index, byPixels: [deltaX * step, deltaY * step],
            imageSize: [Double(imageSize.width), Double(imageSize.height)]
        )
        guard moved != points else { return true }  // at the page's edge: nothing to send, the key is still ours
        reshapeSegment(index: ref.boxIndex, ref.target, to: moved)
        return true
    }

    /// DRAW a polygon or baseline with the Shape tool: `segment.create` on the shown pass, ⌘Z. Only on a
    /// segment pass (an imported page); a page drawn from an artifact keeps its box-only regions path.
    func drawSegmentShape(_ kind: SegmentShapes.DrawKind, points: [[Double]]) {
        guard let passId = shownArtifactlessPassId, let documentId, let store = segmentEditStore else {
            Self.logger.notice("Draw \(kind.title, privacy: .public) not sent: the shown boxes are not a segment pass")
            return
        }
        let onThePass = store.segments(documentId: documentId).filter { $0.passId == passId }
        // A line lands in the region that holds most of it; none, and it stays at page level (no guessing).
        let region = kind == .baseline ? SegmentShapes.containingRegion(for: points, among: onThePass) : nil
        runSegmentEdit(
            SegmentShapes.create(
                kind, points: points, documentId: documentId, passId: passId, onPass: onThePass.first,
                parentSegmentId: region?.id
            ),
            documentId: documentId, name: "Draw \(kind.title)"
        )
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

    /// The Segment menu on the selection (#5157), on any page whose boxes are segments: one audited
    /// `segment.update_many`, ⌘Z.
    func setSelectedSegments(_ attribute: SegmentEdit.Attribute) {
        guard let documentId else { return }
        runSegmentEdit(
            SegmentEdit.set(attribute, on: selectedSegments(documentId)), documentId: documentId, name: "Set Segment"
        )
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
