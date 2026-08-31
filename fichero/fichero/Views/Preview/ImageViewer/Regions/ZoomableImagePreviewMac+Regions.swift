#if os(macOS)
import SwiftUI

// MARK: - Region curation verbs (Daniel, 2026-08-29: regions as first-class)
//
// Selection lives on `RegionSelection.shared` (the FocusedArtifact idiom, so
// the inspector's region rows and this preview stay in sync); ephemeral
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

    /// The interactive layer + its context menu. Mounted whenever an image is
    /// measured; a tap on empty ground clears selection, which is the
    /// click-away-deselects ruling, not an accident.
    @ViewBuilder
    var regionInteractionLayer: some View {
        if let documentId {
            RegionInteractionLayer(
                boxes: displayedGeometryBoxes,
                allBoxes: ocrGeometry?.boxes ?? [],
                visible: geometry.visible,
                artifactId: ocrGeometryArtifactId,
                documentId: documentId,
                marquees: windowState?.previewMarquees,
                imagePixelSize: imageSize == .zero ? nil : imageSize,
                isAddingRegion: isAddingRegion,
                onMoveCommit: { index, bbox in commitRegionMove(index: index, bbox: bbox) }
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
        if let marquees = windowState?.previewMarquees,
           marquees.documentId == documentId, !marquees.isEmpty {
            Button(
                marquees.count == 1
                    ? "New Region from Selection"
                    : "New Regions from \(marquees.count) Selections"
            ) {
                promoteMarquees()
            }
            Button("Clear Selections") { marquees.clear() }
        }
        let selection = RegionSelection.shared
        if let artifactId = ocrGeometryArtifactId, selection.artifactId == artifactId {
            if selection.count >= 2 {
                Button("Combine \(selection.count) Regions") { combineSelectedRegions() }
            }
            if selectionIsWordLevel {
                // Word-boundary marquee (Daniel, 2026-08-30, ruling 2): the
                // selected WORDS become regions — one strip per line, the
                // same grammar as promoting marquees.
                Button("New Region from Words") { promoteSelectedWords() }
            }
            if !selection.isEmpty {
                Button(
                    selection.count == 1 ? "Delete Region" : "Delete \(selection.count) Regions",
                    role: .destructive
                ) { deleteSelectedRegions() }
            }
        }
    }

    // MARK: Verbs

    /// MOVE: committed on mouse-up. Indices are stable across a move, so the
    /// selection survives; the boxes re-render from the response geometry.
    func commitRegionMove(index: Int, bbox: [Double]) {
        guard let artifactId = ocrGeometryArtifactId,
              let documentId, let artifactService else { return }
        Task {
            do {
                let updated = try await artifactService.moveRegion(
                    artifactId: artifactId, documentId: documentId,
                    index: index, bbox: bbox
                )
                ocrGeometry = updated.ocrGeometry
            } catch {
                Self.logger.error("Region move failed: \(String(describing: error))")
            }
        }
    }

    /// DELETE: server-side soft (undoable action + curation log). The held
    /// indices are meaningless afterwards, so the selection clears.
    func deleteSelectedRegions() {
        let selection = RegionSelection.shared
        guard let artifactId = ocrGeometryArtifactId,
              selection.artifactId == artifactId, !selection.isEmpty,
              let documentId, let artifactService else { return }
        let indices = selection.indices
        Task {
            do {
                let updated = try await artifactService.deleteRegions(
                    artifactId: artifactId, documentId: documentId, indices: indices
                )
                ocrGeometry = updated.ocrGeometry
                selection.invalidate(artifactId: artifactId)
            } catch {
                Self.logger.error("Region delete failed: \(String(describing: error))")
            }
        }
    }

    /// COMBINE: union bbox + texts in reading order — the ORDER is the
    /// server's call, so click order stays free.
    func combineSelectedRegions() {
        let selection = RegionSelection.shared
        guard let artifactId = ocrGeometryArtifactId,
              selection.artifactId == artifactId, selection.count >= 2,
              let documentId, let artifactService else { return }
        let indices = selection.indices
        Task {
            do {
                let updated = try await artifactService.combineRegions(
                    artifactId: artifactId, documentId: documentId, indices: indices
                )
                ocrGeometry = updated.ocrGeometry
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
    func promoteMarquees() {
        guard let documentId, let artifactService,
              let marquees = windowState?.previewMarquees,
              marquees.documentId == documentId, !marquees.isEmpty else { return }
        let rects = marquees.readingOrderRects
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
                for rect in rects {
                    latest = try await artifactService.addRegion(
                        artifactId: artifactId, documentId: documentId, bbox: rect
                    )
                }
                if let latest {
                    ocrGeometry = latest.ocrGeometry
                    ocrGeometryArtifactId = latest.id
                }
                marquees.clear()
                isAddingRegion = false
            } catch {
                Self.logger.error("Region promote failed: \(String(describing: error))")
            }
        }
    }

    /// True when every selected index is a WORD-level box in the displayed
    /// geometry — the only selection "New Region from Words" can honestly
    /// promote (line rows already ARE regions).
    var selectionIsWordLevel: Bool {
        let selection = RegionSelection.shared
        guard let artifactId = ocrGeometryArtifactId, selection.artifactId == artifactId,
              !selection.isEmpty, let boxes = ocrGeometry?.boxes else { return false }
        return selection.indices.allSatisfy { boxes.indices.contains($0) && boxes[$0].level == "word" }
    }

    /// PROMOTE the word selection to regions (ruling 2): the selected words
    /// group into one strip per line via the same word-snap math a highlight
    /// uses, and each strip lands as its own region — like `promoteMarquees`,
    /// but word-bounded instead of hand-drawn.
    func promoteSelectedWords() {
        let selection = RegionSelection.shared
        guard let artifactId = ocrGeometryArtifactId, selection.artifactId == artifactId,
              !selection.isEmpty, let documentId, let artifactService,
              let geometry = ocrGeometry else { return }
        let words = selection.indices
            .filter { geometry.boxes.indices.contains($0) }
            .map { geometry.boxes[$0] }
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
                    )
                }
                if let latest {
                    ocrGeometry = latest.ocrGeometry
                    ocrGeometryArtifactId = latest.id
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
        if let marquees = windowState?.previewMarquees, marquees.selectedIndex != nil {
            marquees.removeSelected()
            return
        }
        deleteSelectedRegions()
    }

    /// Esc: everything ephemeral goes — add mode, marquees, selection.
    func clearEphemeralRegionState() {
        isAddingRegion = false
        windowState?.previewMarquees.clear()
        RegionSelection.shared.clear()
    }
}

#endif
