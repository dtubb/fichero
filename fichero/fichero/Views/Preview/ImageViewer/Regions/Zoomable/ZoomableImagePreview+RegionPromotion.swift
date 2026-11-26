#if os(macOS)
import SwiftUI

// Promoting marquees and words to regions, the delete key, verb notifications and key handling,
// split from ZoomableImagePreviewMac+Regions.swift.

extension ZoomableImagePreview {
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
        if refusesEditOnMappedRendition() { return }
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
        // A page shown from a segment pass gets its region ON that pass (`segment.create`, ⌘Z). A regions artifact
        // made here became a pass ranked below the working one, and the box vanished on the next load (#6426).
        if SegmentShapes.drawsMarqueesOnPass(passShown: shownArtifactlessPassId != nil, onlyIndex: onlyIndex) {
            drawMarqueesAsSegments(rects, clearing: marquees)
            return
        }
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
                finishPromotion(of: marquees, onlyIndex: onlyIndex)
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
        if refusesEditOnMappedRendition() { return }
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
            selectionCount: regionSelection.count,
            pointPressed: isEditingSegments && windowState?.selectedShapePoint?.documentId == documentId
                && windowState?.selectedShapePoint != nil,
            cutMarkPicked: isEditingSegments && windowState?.selectedCutMark != nil
        ) {
        case .removeMarquee: marquees?.removeSelected()
        case .removeCut: removeSelectedCut()
        case .removePoint: removeSelectedShapePoint()
        case .deleteRegions: deleteSelectedRegions()
        case .nothing: break
        }
    }

    /// The segment-editing mode for this pane's window (#5114). No window state, no mode:
    /// a headless host reads, it does not edit.
    var isEditingSegments: Bool { windowState?.isEditingSegments ?? false }

    /// The region types the engine offers for this page; empty until the page's segments are read.
    var shownRegionTypes: [RegionTypeChoice] {
        documentId.flatMap { segmentEditStore?.regionTypesByDocument[$0] } ?? []
    }

    /// What the menu bar's Segment menu acts on (#5229): this pane's own verbs, nothing new.
    var segmentMenuTarget: SegmentMenuTarget {
        SegmentMenuTarget(
            isEditing: isEditingSegments, selectionCount: regionSelection.count,
            toggleEditing: { windowState?.isEditingSegments.toggle() },
            canSelectAll: ocrGeometry?.boxes.isEmpty == false, selectAll: { selectAllGeometryForArmedTool() },
            selectSameKind: { selectSameKind() },
            nextDoubtful: { selectNextDoubtful() },
            delete: { deleteSelectedRegions() }, join: { combineSelectedRegions() },
            selectionHasBaselines: selectionHasBaselines, redraw: { redrawSelectedOutlines() },
            splitAtPoint: { splitSelectedLineAtLastPoint() },
            simplify: { simplifySelectedSegments() },
            convertToBox: { convertSelectedToBox() },
            convertToLine: { convertSelected(to: "line") },
            convertToRegion: { convertSelected(to: "region") },
            addVerb: documentId.flatMap { SegmentShapes.addLevel(for: selectedSegments($0)) },
            addDrawn: { addDrawnInSelection() },
            makeRegion: { makeRegionFromSelectedLines() },
            ungroupRegion: { ungroupSelectedRegions() },
            cutWords: { cutWordsOnSelectedLines() },
            cutCharacters: { cutCharactersInSelectedWords() },
            hasBrokenWords: windowState?.brokenWords.isEmpty == false,
            joinBrokenWords: { joinBrokenWords() },
            addBaseline: { addBaselineToSelectedLines() },
            types: shownRegionTypes,
            attributeToLastHand: { attributeSelectedToLastHand() },
            removeHand: { removeHandFromSelected() },
            apply: { setSelectedSegments($0) }
        )
    }

    /// The head's markup-row verbs, on the selection alone.
    func handleRegionVerb(_ note: Notification) {
        guard let raw = note.object as? String, let verb = PreviewRegionVerb(rawValue: raw) else { return }
        switch SegmentEditingMode.action(for: verb, selectionCount: regionSelection.count) {
        case .delete: deleteSelectedRegions()
        case .combine: combineSelectedRegions()
        case nil: break
        }
    }

    /// K (the Knife, `segment-editor.split-knife`) or M (the Marker, `segment-editor.marker`) down and up in Edit
    /// Segments: held for one stroke, or chosen by a tap. Ignored outside Edit Segments and with a modifier held, so ⌘K,
    /// ⇧⌘M and the rest keep their jobs.
    func holdSpringTool(_ press: KeyPress) -> KeyPress.Result {
        guard let windowState else { return .ignored }
        if let result = chooseModeTool(press, windowState) { return result }
        if press.key == KeyEquivalent("b") {
            guard let held = KnifeStroke.held(
                pressed: press.phase == .down, modifiers: press.modifiers, isEditing: isEditingSegments, wasHeld: windowState.brushHeld
            ) else { return .ignored }
            if held { windowState.pressBrushKey() } else { windowState.letGoOfBrushKey() }
            return .handled
        }
        let marker = press.key == KeyEquivalent("m")
        guard let held = KnifeStroke.held(
            pressed: press.phase == .down, modifiers: press.modifiers, isEditing: isEditingSegments,
            wasHeld: marker ? windowState.markerHeld : windowState.knifeHeld
        ) else { return .ignored }
        switch (marker, held) {
        case (true, true): windowState.pressMarkerKey()
        case (true, false): windowState.letGoOfMarkerKey()
        case (false, true): windowState.pressKnifeKey()
        case (false, false): windowState.letGoOfKnifeKey()
        }
        return .handled
    }

    /// O (Order) and P (Paintbrush), the tools that are modes rather than spring-loaded, and [ / ] for the Brush's
    /// size or the Paintbrush's width; nil for any other key.
    private func chooseModeTool(_ press: KeyPress, _ windowState: WindowState) -> KeyPress.Result? {
        if press.key == KeyEquivalent("o") {
            // The Order tool is a mode, not spring-loaded: O chooses it and O again leaves it (sending the clicks).
            guard press.phase == .down, isEditingSegments, press.modifiers.subtracting(.capsLock).isEmpty else { return .ignored }
            windowState.chooseSegmentTool(windowState.orderArmed ? nil : .order)
            return .handled
        }
        if press.key == KeyEquivalent("[") || press.key == KeyEquivalent("]") {
            // The Brush's size (`segment-editor.select-brush`) or the Paintbrush's width, while either is chosen.
            guard press.phase == .down else { return .ignored }
            let larger = press.key == KeyEquivalent("]")
            if windowState.paintArmed { windowState.resizePaint(larger: larger); return .handled }
            guard windowState.brushArmed || windowState.brushHeld else { return .ignored }
            windowState.resizeBrush(larger: larger)
            return .handled
        }
        if press.key == KeyEquivalent("p") {
            // The Paintbrush is a mode (`segment-editor.paintbrush`): P chooses it, P again puts it down.
            guard press.phase == .down, isEditingSegments, press.modifiers.subtracting(.capsLock).isEmpty else { return .ignored }
            windowState.chooseSegmentTool(windowState.paintArmed ? nil : .paint)
            return .handled
        }
        return nil
    }

    /// Return while a polygon or baseline is being drawn: finish it, as a click on its first point or a double-click does.
    /// Ignored (the key keeps its other jobs) with no drawing or too few points.
    func finishShapeDrawingFromKey() -> KeyPress.Result {
        // Return leaves the Order tool, which sends its clicks (`segment-editor.order-by-clicking`).
        if windowState?.orderArmed == true { windowState?.chooseSegmentTool(nil); return .handled }
        guard let windowState, !windowState.drawingPoints.isEmpty else { return .ignored }
        if let points = windowState.closeDrawing() { drawSegmentShape(windowState.shapeKind, points: points) }
        return .handled
    }

    /// Esc: everything ephemeral goes — add mode, marquees, selection.
    func clearEphemeralRegionState() {
        // Escape during a polygon or baseline drawing abandons just the drawing, nothing else.
        if windowState?.abandonDrawing() == true { return }
        // Then the Knife chosen by K or the tool row goes down, back to Select; the selection stays (one thing per press).
        if let windowState, windowState.activeSegmentTool != nil {
            windowState.chooseSegmentTool(nil)
            return
        }
        isAddingRegion = false
        windowState?.previewMarquees.clear()
        regionSelection.clear()
    }
}

#endif
