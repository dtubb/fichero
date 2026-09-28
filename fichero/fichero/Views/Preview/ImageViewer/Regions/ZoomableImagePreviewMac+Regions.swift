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
        guard ocrBoxesEnabled, let ocrGeometry,
              geometryFrameMatchesDisplay(ocrGeometry) else { return [] }
        return ocrGeometry.displayIndexedBoxes
    }

    /// What the document overlay draws INSIDE the image view (#5020, #5142): the boxes the canvas
    /// shows and the selected ones, from the SAME two lists the hit-test and the region layer use,
    /// so a click, its box and its highlight cannot disagree about which box it is.
    /// This page's ephemeral marquees -- a marquee drawn on another document is not this page's.
    var currentMarquees: [[Double]] {
        guard let marquees = windowState?.previewMarquees, marquees.documentId == documentId else { return [] }
        return marquees.rects
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
        return DocumentOverlay(
            boxes: shown.map {
                .init(bbox: $0.box.bbox, confidence: $0.box.confidence, text: $0.box.text,
                      showsText: inlineTextEnabled && OCRBoxConfidence.drawsInlineText($0.box.confidence),
                      shapes: $0.box.shapes)
            },
            selected: selected,
            selectedShapes: selectedIndices.map { all[$0].shapes },
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
            isFocusedPane: windowState?.focusedRegionSelection === regionSelection
        )
    }

    /// The full box list, or nothing when the geometry names a frame other
    /// than the pixels on screen — never draw or select against a frame that
    /// is not the one shown.
    var frameMatchedGeometryBoxes: [OCRGeometryBox] {
        guard let ocrGeometry, geometryFrameMatchesDisplay(ocrGeometry) else { return [] }
        return ocrGeometry.boxes
    }

    /// ⌘A (Daniel, 2026-08-31): with the text tool armed, every WORD box;
    /// otherwise every box the overlay is SHOWING (visible-surface ruling —
    /// you select what you can see), falling back to the whole geometry when
    /// the overlay is off.
    func selectAllGeometryForArmedTool() {
        guard let artifactId = ocrGeometrySelectionScope else { return }
        let all = frameMatchedGeometryBoxes
        guard !all.isEmpty else { return }
        let indices: [Int]
        switch windowState?.activeMarkupTool {
        case .textSelect, .wordSelect:
            let words = all.indices.filter { all[$0].level == "word" }
            indices = words.isEmpty ? Array(all.indices) : words
        default:
            let shown = displayedGeometryBoxes.map(\.index)
            indices = shown.isEmpty ? Array(all.indices) : shown
        }
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
                selection: regionSelection
            )
            .contextMenu { regionContextMenu }
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
        // Clearing marquees is ephemeral and stays; naming one INTO a region writes a
        // segment, so it waits for the mode (#5114).
        if let documentId, let marquees = windowState?.previewMarquees,
           marquees.documentId == documentId, !marquees.isEmpty, !isEditingSegments {
            Button("Clear Selections") { marquees.clear() }
                .help("Discard the drawn selections without saving them")
        }
        if let documentId, let marquees = windowState?.previewMarquees,
           marquees.documentId == documentId, !marquees.isEmpty, isEditingSegments {
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
        if isEditingSegments, let scope = ocrGeometrySelectionScope, selection.artifactId == scope {
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
            actionName: actionName, undoManager: undoManager,
            actionsService: actionStore?.actionsService
        )
    }

    // MARK: Verbs

    /// MOVE: committed on mouse-up. Indices are stable across a move, so the
    /// selection survives; the boxes re-render from the response geometry.
    func commitRegionMove(index: Int, bbox: [Double]) {
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
            } catch {
                Self.logger.error("Region delete failed: \(String(describing: error))")
            }
        }
    }

    /// COMBINE: union bbox + texts in reading order — the ORDER is the
    /// server's call, so click order stays free.
    func combineSelectedRegions() {
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

    /// PROMOTE: each marquee becomes its OWN region, in reading order — the
    /// diary-entry pattern (one entry, one bbox, later its own transcription).
    /// A page with no geometry artifact first gets a bare `regions` artifact
    /// to hold the hand-drawn boxes. The regions are created WITHOUT text: no
    /// one-crop OCR call is cheaply reachable today (detect/transcribe run as
    /// workflow passes), so an empty text is the honest value.
    ///
    /// Daniel, 2026-08-31 ("if we draw it, we should be able to save it, and
    /// double click on it to be taken to a new region"): a promoted marquee
    /// now lands as BOTH a geometry region — the box the preview draws and
    /// the curation verbs address by index — and a region CHILD NODE
    /// (`image.crop_child`), which is what a double-click can be taken to.
    /// Two writes, deliberately: the box alone has nowhere to go, and the
    /// node alone would make the drawn region vanish the moment it was saved.
    ///
    /// - Parameters:
    ///   - name: the user's name for the region; empty saves it unnamed.
    ///   - onlyIndex: promote just that marquee (its own badge), or nil for
    ///     the whole set in reading order (the right-click verb).
    func promoteMarquees(named name: String = "", onlyIndex: Int? = nil) {
        guard let documentId, let artifactService,
              let marquees = windowState?.previewMarquees,
              marquees.documentId == documentId, !marquees.isEmpty else { return }
        let rects: [[Double]]
        if let onlyIndex, marquees.rects.indices.contains(onlyIndex) {
            rects = [marquees.rects[onlyIndex]]
        } else {
            rects = marquees.readingOrderRects
        }
        let pixelSize = marquees.imagePixelSize
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        Task {
            do {
                let artifactId: String
                if let existing = ocrGeometryArtifactId {
                    artifactId = existing
                } else {
                    artifactId = try await artifactService.createRegionsArtifact(
                        documentId: documentId
                    ).id
                }
                var latest: Artifact?
                for (offset, rect) in rects.enumerated() {
                    // One engine action per marquee, so ⌘Z is not registered here: undoing
                    // a promotion of three marquees would need three steps, and offering
                    // the first as "Undo Promote" would undo one region of three. A bulk
                    // add is the fix, as `segment.update_many` was for attributes.
                    latest = try await artifactService.addRegion(
                        artifactId: artifactId, documentId: documentId, bbox: rect
                    ).artifact
                    await materializeRegionChild(
                        parentId: documentId, rect: rect, pixelSize: pixelSize,
                        name: Self.childName(trimmed, offset: offset, total: rects.count)
                    )
                }
                if let latest {
                    ocrGeometry = latest.ocrGeometry
                    ocrGeometryArtifactId = latest.id
                    // FOCUS the artifact we just wrote (Daniel, 2026-09-02:
                    // "I added regions and then they disappear"). The next
                    // geometry reload re-runs the authority ladder, where a
                    // newer transcription outranks this regions artifact —
                    // the drawn boxes vanished on the very next reload.
                    // Focus outranks the ladder, so what you drew stays up.
                    FocusedArtifact.shared.select(
                        latest.id, documentId: documentId, in: [latest]
                    )
                }
                if onlyIndex == nil {
                    marquees.clear()
                    isAddingRegion = false
                } else if let onlyIndex {
                    marquees.selectedIndex = onlyIndex
                    marquees.removeSelected()
                }
            } catch {
                Self.logger.error("Region promote failed: \(String(describing: error))")
            }
        }
    }

    /// True when every selected index is a WORD-level box in the displayed
    /// geometry — the only selection "New Region from Words" can honestly
    /// promote (line rows already ARE regions).
    var selectionIsWordLevel: Bool {
        let selection = regionSelection
        guard let artifactId = ocrGeometryArtifactId, selection.artifactId == artifactId,
              !selection.isEmpty, let boxes = ocrGeometry?.boxes else { return false }
        let resolved = selection.resolvedIndices(in: boxes)
        return !resolved.isEmpty && resolved.allSatisfy { boxes[$0].level == "word" }
    }

    /// PROMOTE the word selection to regions (ruling 2): the selected words
    /// group into one strip per line via the same word-snap math a highlight
    /// uses, and each strip lands as its own region — like `promoteMarquees`,
    /// but word-bounded instead of hand-drawn.
    func promoteSelectedWords() {
        let selection = regionSelection
        guard let artifactId = ocrGeometryArtifactId, selection.artifactId == artifactId,
              !selection.isEmpty, let documentId, let artifactService,
              let geometry = ocrGeometry else { return }
        let words = selection.resolvedIndices(in: geometry.boxes).map { geometry.boxes[$0] }
        guard !words.isEmpty else { return }
        // The words' union as the "drag": snappedRects then yields one
        // strip per line of exactly these words. Bounded sub-expressions —
        // one chained array literal here timed out the type-checker.
        let minX: Double = words.map { $0.bbox[0] }.min() ?? 0
        let minY: Double = words.map { $0.bbox[1] }.min() ?? 0
        let maxX: Double = words.map { $0.bbox[0] + $0.bbox[2] }.max() ?? 0
        let maxY: Double = words.map { $0.bbox[1] + $0.bbox[3] }.max() ?? 0
        let union: [Double] = [minX, minY, maxX - minX, maxY - minY]
        let strips = AnnotationWordSnap.snappedRects(
            drag: union, words: words, lines: geometry.lineBoxes
        )
        Task {
            do {
                var latest: Artifact?
                for strip in strips {
                    latest = try await artifactService.addRegion(
                        artifactId: artifactId, documentId: documentId, bbox: strip
                    ).artifact
                }
                if let latest {
                    ocrGeometry = latest.ocrGeometry
                    ocrGeometryArtifactId = latest.id
                    // Same stay-visible rule as promoteMarquees (2026-09-02).
                    FocusedArtifact.shared.select(
                        latest.id, documentId: documentId, in: [latest]
                    )
                }
                selection.invalidate(artifactId: artifactId)
            } catch {
                Self.logger.error("Region-from-words promote failed: \(String(describing: error))")
            }
        }
    }

    /// Delete key: the picked marquee first (most ephemeral, most recently
    /// made), else the selected persisted regions.
    func handleRegionDeleteKey() {
        let marquees = windowState?.previewMarquees
        switch SegmentEditingMode.deleteKey(
            marqueePicked: marquees?.selectedIndex != nil,
            isEditing: isEditingSegments,
            selectionCount: regionSelection.count
        ) {
        case .removeMarquee: marquees?.removeSelected()
        case .deleteRegions: deleteSelectedRegions()
        case .nothing: break
        }
    }

    /// The segment-editing mode for this pane's window (#5114). No window state, no mode:
    /// a headless host reads, it does not edit.
    var isEditingSegments: Bool { windowState?.isEditingSegments ?? false }

    /// The head's markup-row verbs, gated by the mode.
    func handleRegionVerb(_ note: Notification) {
        guard let raw = note.object as? String, let verb = PreviewRegionVerb(rawValue: raw) else { return }
        switch SegmentEditingMode.action(
            for: verb, isEditing: isEditingSegments, selectionCount: regionSelection.count
        ) {
        case .delete: deleteSelectedRegions()
        case .combine: combineSelectedRegions()
        case nil: break
        }
    }

    /// Esc: everything ephemeral goes — add mode, marquees, selection.
    func clearEphemeralRegionState() {
        isAddingRegion = false
        windowState?.previewMarquees.clear()
        regionSelection.clear()
    }
}

#endif
