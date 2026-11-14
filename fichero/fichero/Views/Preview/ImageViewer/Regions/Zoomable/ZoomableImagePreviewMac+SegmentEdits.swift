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

    var segmentEditStore: SegmentStore? {
        segmentService.map { SegmentStore.shared(for: $0) }
    }

    /// MOVE the selection by dragging one of its boxes (`segment-editor.group-drag`): when every selected box is a saved
    /// segment and the dragged one is among them, ONE `segment.translate` by the drag's offset, outlines and baselines
    /// with their boxes. True when handled here.
    func moveSelectedSegments(draggedIndex: Int, to bbox: [Double]) -> Bool {
        guard let documentId, let boxes = ocrGeometry?.boxes, boxes.indices.contains(draggedIndex),
              let draggedId = boxes[draggedIndex].segmentId, bbox.count >= 2, boxes[draggedIndex].bbox.count >= 2 else { return false }
        let segments = selectedSegments(documentId)
        guard segments.contains(where: { $0.id == draggedId }), segments.allSatisfy({ $0.version != nil }) else { return false }
        let old = boxes[draggedIndex].bbox
        runSegmentEdit(
            SegmentEdit.translate(segments, by: [bbox[0] - old[0], bbox[1] - old[1]]), documentId: documentId,
            name: segments.count == 1 ? "Move Segment" : "Move Segments"
        )
        return true
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
                    actionName: "Convert Page", actionsService: actionsService, steps: windowSteps,
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
    func shownSegment(at index: Int, _ documentId: String, _ store: SegmentStore) -> Segment? {
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
        guard let ref = windowState?.selectedShapePoint,
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

    /// ⌫ on the shape point last pressed (`segment-editor.vertices`): that point goes, as an ⌥-click does, one reshape and
    /// ⌘Z; a shape already at its fewest points keeps it and the page says why.
    func removeSelectedShapePoint() {
        guard let windowState, let ref = windowState.selectedShapePoint, let documentId, ref.documentId == documentId,
              let store = segmentEditStore, let segment = shownSegment(at: ref.boxIndex, documentId, store),
              let points = SegmentShapes.points(of: segment, ref.target) else { return }
        guard let fewer = SegmentShapes.removing(points, index: ref.index, ref.target) else {
            windowState.segmentNotice = "A shape keeps at least \(ref.target.minimumPoints) points"
            return
        }
        windowState.selectedShapePoint = nil
        reshapeSegment(index: ref.boxIndex, ref.target, to: fewer)
    }

    /// Up/Down with segments selected move the selection through the page in reading order (#6457), everywhere at once
    /// through `InspectorPath.select`. False when nothing moves, so the arrow keeps its panning.
    func stepSegmentSelection(_ step: Int, extend: Bool) -> Bool {
        guard let documentId, let store = segmentEditStore else { return false }
        return InspectorPath.stepSelection(by: step, extend: extend, selection: regionSelection, documentId: documentId, store: store)
    }

    /// DRAW a polygon or baseline with the Shape tool: `segment.create` on the shown pass, ⌘Z. Only on a
    /// segment pass (an imported page); a page drawn from an artifact keeps its box-only regions path.
    func drawSegmentShape(_ kind: SegmentShapes.DrawKind, points: [[Double]]) {
        guard let passId = shownArtifactlessPassId, let documentId, let store = segmentEditStore else {
            Self.logger.notice("Draw \(kind.title, privacy: .public) not sent: the shown boxes are not a segment pass")
            return
        }
        let onThePass = store.segments(documentId: documentId).filter { $0.passId == passId }
        windowState?.lastDrawnKind = kind == .baseline ? "line" : "region"
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

    /// DRAW with the Marker (`segment-editor.marker`): one `segment.create` on the shown pass, the stroke simplified by the
    /// engine; closed, a segment of the kind last drawn; open, a line on it as a baseline, its outline from the ink, in
    /// the region holding most of it. ⌘Z.
    func drawMarkerStroke(_ stroke: [[Double]], closed: Bool) {
        guard let passId = shownArtifactlessPassId, let documentId, let store = segmentEditStore else {
            Self.logger.notice("Marker stroke not sent: the shown boxes are not a segment pass")
            return
        }
        let onThePass = store.segments(documentId: documentId).filter { $0.passId == passId }
        let kind = windowState?.lastDrawnKind ?? "region"
        runSegmentEdit(
            MarkerStroke.create(
                stroke, closed: closed, closedKind: kind, on: StrokeTarget(
                    documentId: documentId, passId: passId, onPass: onThePass.first,
                    parentSegmentId: closed ? nil : SegmentShapes.containingRegion(for: stroke, among: onThePass)?.id
                )
            ),
            documentId: documentId, name: "Draw with Marker"
        )
        if !closed { windowState?.lastDrawnKind = "line" }
    }

    /// The Order tool left (`segment-editor.order-by-clicking`): its clicks as ONE `reading_order.sequence` in the pass's
    /// `as-written` order, one ⌘Z; the page says why when there is no such order.
    func sendOrderClicks() {
        // Every Preview pane of the window hears the tool put down; only the one showing the clicked segments takes them.
        guard let windowState, let documentId, let store = segmentEditStore, let readingOrderService,
              let firstClick = windowState.orderClicks.first,
              let passId = store.segments(documentId: documentId).first(where: { $0.id == firstClick })?.passId,
              let taken = windowState.takeOrderClicks() else { return }
        let (clicks, after) = (taken.segmentIds, taken.after)
        Task {
            do {
                let orders = try await readingOrderService.orders(documentId: documentId)
                let planned = SegmentEdit.sequence(clicks, after: after, passId: passId, orders: orders)
                if case .failure(let refusal) = planned { windowState.segmentNotice = SegmentMover.problem(refusal) }
                runSegmentEdit(planned, documentId: documentId, name: "Set Reading Order")
            } catch {
                Self.logger.error("Set Reading Order not sent: \(error.localizedDescription, privacy: .public)")
            }
        }
    }

    /// PAINT a line (`segment-editor.paintbrush`): one `segment.create` with the brush's stroke, in the region holding most
    /// of it; the engine makes the outline and the baseline. ⌘Z.
    func drawPaintStroke(_ stroke: [[Double]], widthPixels: Double) {
        guard let passId = shownArtifactlessPassId, let documentId, let store = segmentEditStore else {
            Self.logger.notice("Paintbrush stroke not sent: the shown boxes are not a segment pass")
            return
        }
        let onThePass = store.segments(documentId: documentId).filter { $0.passId == passId }
        runSegmentEdit(
            PaintbrushStroke.create(
                stroke, widthPixels: widthPixels, on: StrokeTarget(
                    documentId: documentId, passId: passId, onPass: onThePass.first,
                    parentSegmentId: SegmentShapes.containingRegion(for: stroke, among: onThePass)?.id
                )
            ),
            documentId: documentId, name: "Paint Line"
        )
        windowState?.lastDrawnKind = "line"
    }

    /// MOVE A CUT by its mark (`segment-editor.cut-marks-editable`): one `segment.move_cut`, the cut a person's now. ⌘Z.
    func moveCut(_ firstId: String, _ secondId: String, to place: Double) {
        guard let documentId, let store = segmentEditStore else { return }
        let versions = Dictionary(
            store.segments(documentId: documentId).filter { $0.id == firstId || $0.id == secondId }
                .compactMap { segment in segment.version.map { (segment.id, $0) } },
            uniquingKeysWith: { first, _ in first }
        )
        runSegmentEdit(
            SegmentEdit.moveCut(firstId: firstId, secondId: secondId, place: place, versions: versions),
            documentId: documentId, name: "Move Cut"
        )
    }

    /// REMOVE THE CUT last clicked (`segment-editor.cut-marks-editable`): its two pieces joined as one, one ⌘Z.
    func removeSelectedCut() {
        guard let windowState, let pair = windowState.selectedCutMark, let documentId, let store = segmentEditStore else { return }
        windowState.selectedCutMark = nil
        let byId = Dictionary(store.segments(documentId: documentId).map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let pieces = pair.compactMap { byId[$0] }
        guard pieces.count == 2 else { return }
        runSegmentEdit(SegmentEdit.join(pieces, asLines: true), documentId: documentId, name: "Remove Cut")
    }

    /// DELETE the selected boxes on an artifact-less pass. True when handled here.
    func deleteSelectedSegments() -> Bool {
        guard shownArtifactlessPassId != nil, let documentId else { return false }
        runSegmentEdit(SegmentEdit.delete(selectedSegments(documentId)), documentId: documentId, name: "Delete Segments")
        regionSelection.clear()
        return true
    }

    /// DELETE the selected boxes when every one IS a segment (#6419): the one `segment.delete` batch (`SegmentDeleter`), one ⌘Z,
    /// so the segment goes with its box on a page that also has a result artifact. False hands the delete to the artifact route.
    func deleteSelectedBoxesAsSegments() -> Bool {
        guard let documentId, let store = segmentEditStore else { return false }
        let selection = regionSelection
        let segments = SegmentDeleter.segments(
            SegmentDeleter.selectedIds(selection, documentId: documentId, store: store), documentId: documentId, store: store
        )
        guard PreviewRegionDelete.door(
            selectionCount: selection.count, segmentCount: segments.count, versionedCount: segments.filter { $0.version != nil }.count
        ) == .segments else { return false }
        let actionsService = actionStore?.actionsService, steps = windowSteps
        Task {
            if let problem = await SegmentDeleter.run(
                segments, documentId: documentId, store: store, actionsService: actionsService, steps: steps, clearing: selection
            ) {
                Self.logger.error("Delete Segments failed: \(problem, privacy: .public)")
            }
            await loadOCRGeometry()
        }
        return true
    }

    /// JOIN the selected boxes when every one IS a segment: the segment editor's Merge, outlines, baselines and
    /// readings joined in reading order, across regions (`segment-editor.merge-lines`). The same door Delete takes
    /// (#6419), so a page that also has a result artifact joins its lines too, instead of the artifact's combine (a
    /// union rectangle with the outline and baseline dropped). True when handled here.
    func joinSelectedSegments() -> Bool {
        guard let documentId else { return false }
        let segments = selectedSegments(documentId)
        let onSegments = shownArtifactlessPassId != nil || PreviewRegionDelete.door(
            selectionCount: regionSelection.count, segmentCount: segments.count,
            versionedCount: segments.filter { $0.version != nil }.count
        ) == .segments
        guard onSegments else { return false }
        // Merged regions: their lines now read among the kept region's; the order shows for two seconds.
        let flash = SegmentEdit.joinsRegions(segments)
        runSegmentEdit(SegmentEdit.join(segments, asLines: true), documentId: documentId, name: "Join Segments") { _ in
            if flash { windowState?.flashOrderOverlay() }
        }
        regionSelection.clear()
        return true
    }

    /// REDRAW the selected lines' outlines from their baselines (`segment-editor.regenerate-polygon-from-baseline`):
    /// one audited `segment.regenerate_outline`, one ⌘Z.
    func redrawSelectedOutlines() {
        guard let documentId else { return }
        runSegmentEdit(
            SegmentEdit.redrawOutline(selectedSegments(documentId)), documentId: documentId, name: "Redraw Outline"
        )
    }

    /// CUT every line the Knife's stroke crosses (`segment-editor.split-knife`): one `segment.split` with the
    /// stroke and the versions of the page's lines it reaches, one ⌘Z. The engine says which lines it left alone.
    func knifeCut(_ stroke: [[Double]]) {
        guard let documentId, let store = segmentEditStore else { return }
        runSegmentEdit(
            SegmentEdit.knife(stroke, over: store.segments(documentId: documentId)), documentId: documentId, name: "Cut Lines"
        ) { result in
            windowState?.segmentNotice = SegmentEdit.knifeNotice(
                cut: result.resultListCounts["splits"] ?? 0, leftAlone: result.resultListCounts["left_alone"] ?? 0
            )
        }
    }

    func runSegmentEdit(
        _ planned: Result<SegmentEdit.Call, SegmentEdit.Refusal>, documentId: String, name: String,
        answered: @escaping @MainActor (ActionInvokeResult) -> Void = { _ in }
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
                let result = try await runner.runAnswering(
                    call, documentId: documentId, actionName: name, steps: windowSteps,
                    afterChange: { await loadOCRGeometry() }
                )
                answered(result)
            } catch {
                Self.logger.error("\(name, privacy: .public) failed: \(String(describing: error), privacy: .public)")
            }
        }
    }

    /// One polygon segment per marquee rectangle, drawn on the shown pass (#6426).
    func drawMarqueesAsSegments(_ rects: [[Double]], clearing marquees: PreviewMarqueeSelection) {
        for rect in rects { drawSegmentShape(.polygon, points: SegmentShapes.corners(ofRect: rect)) }
        marquees.clear()
        isAddingRegion = false
    }

    /// After a promotion: the whole set clears the marquees; one marquee is removed on its own.
    func finishPromotion(of marquees: PreviewMarqueeSelection, onlyIndex: Int?) {
        if let onlyIndex {
            marquees.selectedIndex = onlyIndex
            marquees.removeSelected()
        } else {
            marquees.clear()
            isAddingRegion = false
        }
    }
}

#endif
