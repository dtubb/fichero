#if os(macOS)
import SwiftUI

// MARK: - Region curation verbs (Daniel, 2026-08-29: regions as first-class)
//
// Selection lives on THIS pane's `regionSelection` (#5020, ruled 2026-09-27: each pane owns
// its own; the Inspector follows the focused pane via `WindowState.focusedRegionSelection`); ephemeral
// marquees on the per-window `WindowState.previewMarquees` seam. Every
// persistent verb goes through `ArtifactService` — one audited, undoable
// engine action per edit — and re-renders from the RESPONSE geometry rather
// than re-fetching.

extension ZoomableImagePreview {

    /// The boxes the canvas overlay is drawing, with their full-list indices
    /// — the hit-test set for click-to-select. Empty when the layer is off
    /// or the geometry belongs to a different picture than the one shown.
    var displayedGeometryBoxes: [(index: Int, box: OCRGeometryBox)] {
        guard let drawn = drawnGeometry else { return [] }
        // Each level by its own switch: Show Regions, Show Lines, Show Word Bounding Boxes (owner 2026-11-17).
        return drawn.displayIndexedBoxes.filter {
            SegmentOnRendition.isDrawn($0.box) && SegmentHierarchy.shows(SegmentHierarchy.Level(kind: $0.box.level),
                                   regions: regionsEnabled, lines: linesEnabled, words: ocrBoxesEnabled)
        }
    }

    /// What the document overlay draws INSIDE the image view (#5020, #5142): the boxes the canvas
    /// shows and the selected ones, from the SAME two lists the hit-test and the region layer use,
    /// so a click, its box and its highlight cannot disagree about which box it is.
    /// This page's ephemeral marquees -- a marquee drawn on another document is not this page's.
    var currentMarquees: [[Double]] {
        guard let marquees = windowState?.previewMarquees, marquees.documentId == documentId else { return [] }
        return marquees.rects
    }

    /// This page's segment directions, resolved the ONE way the hover label, the inline text and the
    /// magnifier strip all read them: `SegmentStore`'s, from the page text (#5199, #5411). Nil: unresolved.
    var segmentDirections: (String?) -> String? {
        guard let documentId, let segmentService else { return { _ in nil } }
        let resolve = SegmentStore.shared(for: segmentService).directionResolver(documentId: documentId)
        return { (id: String?) -> String? in id.flatMap(resolve) }
    }

    /// Which way the magnifier strip lies: where the person put it, else along most of the page's lines
    /// (#5411, `magnifier.strip-placement-is-the-persons`, `magnifier.strip-follows-line-direction`).
    var magnifierAxis: Axis {
        var directions: [String] = []
        if let documentId, let segmentService {
            directions = Array((SegmentStore.shared(for: segmentService).directionsByDocument[documentId] ?? [:]).values)
        }
        return MagnifierStrip.axis(placement: magnifierPlacement.wrappedValue, lineDirections: directions)
    }

    /// This pane's strip placement, as the strip's menu reads and writes it.
    var magnifierPlacement: Binding<MagnifierStrip.Placement> {
        Binding(get: { MagnifierStrip.placement(in: magnifierStripPlacements, pane: paneLeafId) },
                set: { magnifierStripPlacements = MagnifierStrip.storing($0, in: magnifierStripPlacements, pane: paneLeafId) })
    }

    var documentOverlay: DocumentOverlay {
        let shown = displayedGeometryBoxes
        let all = frameMatchedGeometryBoxes
        let selection = regionSelection
        let selectedIndices = (ocrGeometrySelectionScope != nil && selection.artifactId == ocrGeometrySelectionScope)
            ? selection.resolvedIndices(in: all) : []
        let selected: [[Double]] = selectedIndices.map { all[$0].bbox }
        // The same frame gates the SwiftUI washes had: the entry wash is anchored on the page's
        // own image, the linked words on the geometry they were measured on.
        let linkedFrameMatches = ocrGeometry.map { geometryFrameMatchesDisplay($0) } ?? false
        // Only the inline text reads a box's direction, so the page is indexed only when it is on.
        let direction: (String?) -> String? = inlineTextEnabled ? segmentDirections : { _ in nil }
        var overlay = DocumentOverlay(
            boxes: shown.map { (entry: (index: Int, box: OCRGeometryBox)) -> DocumentOverlay.Box in
                .init(bbox: entry.box.bbox, confidence: entry.box.confidence, text: entry.box.text,
                      showsText: inlineTextEnabled && OCRBoxConfidence.drawsInlineText(entry.box.confidence),
                      shapes: entry.box.shapes, noReading: entry.box.noReading,
                      segmentId: entry.box.segmentId, kind: entry.box.level,
                      parentSegmentId: entry.box.parentSegmentId,
                      tone: entry.box.tone,
                      orderNumber: entry.box.orderNumber,
                      direction: direction(entry.box.segmentId))
            },
            selected: selected,
            selectedSegmentIds: Set(selectedIndices.compactMap { all[$0].segmentId }),
            selectedShapes: selectedIndices.map { all[$0].shapes },
            selectedPoint: selectedShapePoint(in: all),
            entryWashes: annotationFrameMatchesDisplay(nil) ? highlightBoxes : [],
            linkedWashes: linkedFrameMatches ? linkedSelectionBoxes : [],
            marks: shownAnnotationMarks.compactMap { mark in
                guard let bbox = mark.rect, let shape = DocumentOverlay.Mark.shape(for: mark.kind) else { return nil }
                return .init(shape: shape, bbox: bbox, color: AnnotationMarkGeometry.rgba(hex: mark.color))
            },
            selectedMark: shownAnnotationMarks.first { $0.id == FocusedAnnotation.shared.id }?.rect,
            marquees: currentMarquees,
            pickedMarquee: windowState?.previewMarquees.selectedIndex,
            isEditing: windowState?.isEditingSegments == true,
            isFocusedPane: windowState?.focusedRegionSelection === regionSelection,
            documentId: documentId
        )
        overlay.transcriptionFamily = transcriptionFont?.family
        overlay.showsOrderNumbers = showOrderNumbers || windowState?.orderOverlayFlash == true || windowState?.orderArmed == true
        overlay.showsBoundingBoxes = showBoundingBoxes
        overlay.shadeBoxes(byOrder: shadeByOrder)
        return overlay
    }

    /// Where the nudged shape point is now, for its filled handle (Edit Segments only).
    private func selectedShapePoint(in all: [OCRGeometryBox]) -> [Double]? {
        guard let ref = windowState?.selectedShapePoint,
              ref.documentId == documentId, all.indices.contains(ref.boxIndex),
              let points = all[ref.boxIndex].shapes.first(where: { $0.target == ref.target })?.points,
              points.indices.contains(ref.index) else { return nil }
        return points[ref.index]
    }

    /// The full box list of the geometry the picture can draw (`drawnGeometry`: the page's own, or mapped onto the
    /// rendition shown), or nothing when neither is known — never draw or select against a frame that is not the one shown.
    var frameMatchedGeometryBoxes: [OCRGeometryBox] {
        drawnGeometry?.boxes ?? []
    }

    /// ⌘A (Daniel, 2026-08-31): with the text tool armed, every WORD box;
    /// otherwise every box the overlay is SHOWING (visible-surface ruling —
    /// you select what you can see), falling back to the whole geometry when
    /// the overlay is off.
    func selectAllGeometryForArmedTool() {
        guard let artifactId = ocrGeometrySelectionScope, let geometry = ocrGeometry else { return }
        // Selecting is of the page's segments, not of what this picture can draw: on a rendition whose frame is not the
        // geometry's the overlay shows none of them, and Select All used to find nothing (#6448).
        let frameMatches = geometryFrameMatchesDisplay(geometry)
        let all = geometry.boxes
        let isTextTool: Bool
        switch windowState?.activeMarkupTool {
        case .textSelect, .wordSelect: isTextTool = true
        default: isTextTool = false
        }
        let indices = SegmentOnRendition.selectAllIndices(
            levels: all.map(\.level), shown: displayedGeometryBoxes.map(\.index), frameMatches: frameMatches,
            isTextTool: isTextTool
        )
        guard !indices.isEmpty else { return }
        regionSelection.selectAll(indices, artifactId: artifactId, documentId: documentId, in: all)
    }

    /// The interactive layer + its context menu. Mounted whenever an image is
    /// measured; a tap on empty ground clears selection, which is the
    /// click-away-deselects ruling, not an accident.
    @ViewBuilder
    var regionInteractionLayer: some View {
        if let documentId {
            RegionInteractionLayer(
                boxes: displayedGeometryBoxes,
                // FRAME GATE here too (Daniel, 2026-08-31: selected word
                // boxes drawn off the image): the display set checks that
                // the geometry was measured on THESE pixels, but selection
                // highlights read the full list — a geometry from another
                // rendition's frame scattered its boxes beside the page.
                allBoxes: frameMatchedGeometryBoxes,
                visible: geometry.visible,
                // The selection's scope, not the edit target: an imported pass has no artifact and
                // its boxes must still be selectable (#5152). Edits are refused there by
                // `RegionEditTarget` until they go through the segment actions.
                artifactId: ocrGeometrySelectionScope,
                documentId: documentId,
                marquees: windowState?.previewMarquees,
                imagePixelSize: imageSize == .zero ? nil : imageSize,
                renditionId: displayedRenditionId,
                isAddingRegion: isAddingRegion,
                drawsSelection: false,
                drawsSegments: SegmentEditingMode.shapeDrawsSegment(
                    isEditing: windowState?.isEditingSegments == true
                ),
                isAnnotating: isDrawingRegion,
                onAnnotate: { box in
                    createAnnotation(box: box, tool: pendingAnnotationTool)
                },
                pointer: pointerFeed,
                onMoveCommit: { index, bbox in commitRegionMove(index: index, bbox: bbox) },
                onPromote: { name, index in
                    promoteMarquees(named: name, onlyIndex: index)
                },
                onOpenRegion: { index in openRegion(atIndex: index) },
                onReshapeCommit: { index, target, points in reshapeSegment(index: index, target, to: points) },
                drawKind: windowState?.shapeKind ?? .box,
                onDrawShapeCommit: { kind, points in drawSegmentShape(kind, points: points) },
                onDrawBox: { box in drawBoxOfLastKind(box) },
                onKnifeCommit: { stroke in knifeCut(stroke) },
                onMarkerCommit: { stroke, closed in drawMarkerStroke(stroke, closed: closed) },
                onPaintCommit: { stroke, width in drawPaintStroke(stroke, widthPixels: width) },
                onMoveCut: { first, second, place in moveCut(first, second, to: place) },
                lineDrop: { point, command in dropOfSelection(at: point, command: command) },
                onReassignCommit: { target in reassignSelectedLines(into: target) },
                selection: regionSelection
            )
            .contextMenu { regionContextMenu }
            // Simplify's slider (`segment-editor.vertices`): live while held, one action on release.
            // The Simplify slider acts on the pane whose selection the tools row acts on (the focused one).
            .onChange(of: windowState?.simplifyTolerance) { _, tolerance in
                if windowState?.focusedRegionSelection === regionSelection { previewSimplify(tolerance) }
            }
            .onChange(of: windowState?.orderArmed) { _, armed in if armed == false { sendOrderClicks() } }
            .onChange(of: windowState?.simplifyRelease) { _, release in
                if let release, isEditingSegments, windowState?.focusedRegionSelection === regionSelection {
                    simplifySelectedSegments(tolerance: release.tolerance)
                }
            }
        }
    }

    /// The region verbs, as a context menu for now. The better home is the
    /// planned top mode-tools cluster (the toolbar restructure lane) — this
    /// is the minimal honest affordance until that lands.
    @ViewBuilder
    var regionContextMenu: some View {
        Button(isAddingRegion ? "Stop Adding Regions" : "Add Region…") {
            isAddingRegion.toggle()
        }
        // Naming a marquee INTO a region needs no mode: a selection is the edit state (#6413).
        if let documentId, let marquees = windowState?.previewMarquees,
           marquees.documentId == documentId, !marquees.isEmpty {
            // Daniel, 2026-08-31: the right-click verb ASKS for a name now
            // (hence the ellipsis) — it arms the same naming request the
            // pencil badge does, anchored on the first marquee's badge, so
            // both routes commit through one code path.
            Button(
                marquees.count == 1
                    ? "New Region from Selection…"
                    : "New Regions from \(marquees.count) Selections…"
            ) {
                RegionNamingRequest.shared.arm(documentId: documentId, marqueeIndex: nil)
            }
            .help("Name the drawn selection, then save it as a region")
            Button("Clear Selections") { marquees.clear() }
                .help("Discard the drawn selections without saving them")
        }
        let selection = regionSelection
        // Scoped like the selection (#5152): an imported page's boxes are joined and deleted through
        // the segment actions; promoting words is an artifact verb and stays with an artifact.
        if let scope = ocrGeometrySelectionScope, selection.artifactId == scope {
            if selection.count >= 2 {
                Button("Join \(selection.count) Regions") { combineSelectedRegions() }
            }
            if selectionIsWordLevel, ocrGeometryArtifactId != nil {
                // Word-boundary marquee (Daniel, 2026-08-30, ruling 2): the
                // selected WORDS become regions — one strip per line, the
                // same grammar as promoting marquees.
                Button("New Region from Words") { promoteSelectedWords() }
            }
            if !selection.isEmpty {
                // The Segment menu (#5157): kind, direction, text or furniture, on the selection.
                SegmentAttributeMenu(apply: { setSelectedSegments($0) })
                if selectionHasBaselines {
                    Button("Redraw Outline from Baseline") { redrawSelectedOutlines() }
                }
                Button("Convert to Box") { convertSelectedToBox() }
                Button(
                    selection.count == 1 ? "Delete Region" : "Delete \(selection.count) Regions",
                    role: .destructive
                ) { deleteSelectedRegions() }
            }
        }
    }

    // MARK: Undo (`source.editor.system-undo`, #4941)

    /// Register ⌘Z for one region edit, by the audit row the edit itself wrote.
    ///
    /// The engine inverts the row and answers the inverse's own id, which is what the
    /// redo inverts in turn (`ActionUndo` owns that chain). No audit id, no undo manager
    /// or no action store: nothing is registered, because every alternative is
    /// inverting a guessed row — on a shared library, one person undoing another's edit.
    func registerRegionUndo(_ result: RegionEditResult, actionName: String) {
        result.registerUndo(
            actionName: actionName, steps: windowSteps,
            actionsService: actionStore?.actionsService,
            afterChange: { await reloadSegmentsAfterRegionEdit() }
        )
        Task { await reloadSegmentsAfterRegionEdit() }
    }

    // MARK: Verbs

    /// MOVE: committed on mouse-up. Indices are stable across a move, so the
    /// selection survives; the boxes re-render from the response geometry.
    func commitRegionMove(index: Int, bbox: [Double]) {
        if refusesEditOnMappedRendition() { return }
        if moveSelectedSegments(draggedIndex: index, to: bbox) { return }   // the selection, as segments (group drag)
        if moveSegment(index: index, bbox: bbox) { return }   // an imported page (#5152)
        guard let artifactId = RegionEditTarget.forDirectEdit(shownArtifactId: ocrGeometryArtifactId),
              let documentId, let artifactService else { return }
        Task {
            do {
                let updated = try await artifactService.moveRegion(
                    artifactId: artifactId, documentId: documentId,
                    index: index, bbox: bbox
                )
                ocrGeometry = updated.artifact.ocrGeometry
                registerRegionUndo(updated, actionName: "Move Region")
            } catch {
                Self.logger.error("Region move failed: \(String(describing: error))")
            }
        }
    }

    /// DELETE: server-side soft (undoable action + curation log). The held
    /// indices are meaningless afterwards, so the selection clears.
    func deleteSelectedRegions() {
        if deleteSelectedSegments() { return }   // an imported page (#5152)
        if deleteSelectedBoxesAsSegments() { return }   // boxes that are segments: the audited segment.delete (#6419)
        let selection = regionSelection
        guard let artifactId = RegionEditTarget.forSelectionEdit(
                  shownArtifactId: ocrGeometryArtifactId,
                  selectionArtifactId: selection.artifactId,
                  selectionCount: selection.count,
                  minimumCount: 1
              ),
              let documentId, let artifactService else { return }
        // The selected boxes' positions in THIS pane's list, found by identity (#5020).
        let indices = selection.resolvedIndices(in: ocrGeometry?.boxes ?? [])
        guard !indices.isEmpty else { return }
        Task {
            do {
                let updated = try await artifactService.deleteRegions(
                    artifactId: artifactId, documentId: documentId, indices: indices
                )
                ocrGeometry = updated.artifact.ocrGeometry
                registerRegionUndo(updated, actionName: "Delete Regions")
                selection.invalidate(artifactId: artifactId)
                await reloadSegmentsAfterRegionEdit()  // the segments went with their boxes: every surface re-reads them (#6419)
            } catch {
                Self.logger.error("Region delete failed: \(String(describing: error))")
            }
        }
    }

    /// COMBINE: union bbox + texts in reading order — the ORDER is the
    /// server's call, so click order stays free.
    func combineSelectedRegions() {
        if refusesEditOnMappedRendition() { return }
        if joinSelectedSegments() { return }   // an imported page (#5152)
        let selection = regionSelection
        guard let artifactId = RegionEditTarget.forSelectionEdit(
                  shownArtifactId: ocrGeometryArtifactId,
                  selectionArtifactId: selection.artifactId,
                  selectionCount: selection.count,
                  minimumCount: 2
              ),
              let documentId, let artifactService else { return }
        let indices = selection.resolvedIndices(in: ocrGeometry?.boxes ?? [])
        guard indices.count >= 2 else { return }
        Task {
            do {
                let updated = try await artifactService.combineRegions(
                    artifactId: artifactId, documentId: documentId, indices: indices
                )
                ocrGeometry = updated.artifact.ocrGeometry
                registerRegionUndo(updated, actionName: "Join Regions")
                selection.invalidate(artifactId: artifactId)
            } catch {
                Self.logger.error("Region combine failed: \(String(describing: error))")
            }
        }
    }
}

#endif
