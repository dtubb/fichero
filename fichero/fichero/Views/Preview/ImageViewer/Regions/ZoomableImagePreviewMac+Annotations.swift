#if os(macOS)
import SwiftUI

// MARK: - Annotation tools (moved from the main file 2026-08-29, file/type
// length budget — the same members, unchanged; see +ZoomActions for the
// precedent).

extension ZoomableImagePreview {
    /// Annotation tools from the reader toolbar (#2458). Highlight/Note arm a
    /// region draw over the image; the resulting normalized box is persisted as
    /// a bounding-box annotation. Bookmark is a whole-image marker (no region).
    /// internal: the reader toolbar moved to +Overlays.swift (2026-08-23
    /// file-length) and Swift's `private` is FILE-scoped.
    func requestAnnotation(_ tool: ReaderAnnotationTool) {
        switch tool {
        case .highlight, .note, .line:
            pendingAnnotationTool = tool
            isDrawingRegion = true
        case .bookmark:
            // A star marks a PLACE on the page (Daniel, 2026-08-31: "star
            // seems to star document, but not the actual location") — same
            // drag-to-place grammar as highlight/note. Whole-document
            // starring stays with the library row's own star.
            pendingAnnotationTool = .bookmark
            isDrawingRegion = true
        }
    }

    /// Persist a region (or whole-image bookmark) via the typed AnnotationStore.
    ///
    /// `internal` (not `private`) so `boxOverlays` in
    /// ZoomableImagePreviewMac+Overlays.swift can call it — a `private` member
    /// is invisible to an extension in another file, the same reason
    /// `sectionDivider` on ReaderToolbar is internal.
    func createAnnotation(box: [Double]?, tool: ReaderAnnotationTool) {
        guard let documentId else { return }
        let kind: AnnotationKind = {
            switch tool {
            case .highlight:
                // The split-button's underline/strikethrough modes persist
                // as their OWN kinds (Daniel, 2026-08-30) — a strikethrough
                // is a judgement, not a tint.
                switch PreviewHighlightStyle(
                    rawValue: UserDefaults.standard.string(
                        forKey: PreviewHighlightStyle.storageKey) ?? ""
                ) {
                case .underline: return .underline
                case .strikethrough: return .strikethrough
                default: return .highlight
                }
            case .note: return .note
            case .bookmark: return .bookmark
            case .line: return .line
            }
        }()
        // Sticky tool (Daniel, 2026-08-30): while the bar keeps the tool
        // armed, the draw layer stays armed for the next box.
        let sticky = windowState?.activeMarkupTool
        isDrawingRegion = sticky == .highlight || sticky == .note || sticky == .line
            || sticky == .star
        // The highlight split-button's color rides the saved highlight
        // (Daniel, 2026-08-29). Underline/strikethrough save uncolored until
        // a backing kind exists (see the toolbars design report).
        let color: String? = kind == .highlight
            ? PreviewHighlightStyle(
                rawValue: UserDefaults.standard.string(forKey: PreviewHighlightStyle.storageKey) ?? ""
            )?.persistedColor
            : nil
        // Word-boundary snap (Daniel, 2026-08-30): highlight/underline/
        // strikethrough hug the recognised words the drag touched — one
        // strip per line. Free-form kinds (note, line) keep the drawn rect.
        let snapKinds: Set<AnnotationKind> = [.highlight, .underline, .strikethrough]
        let rects: [[Double]?]
        if let box, snapKinds.contains(kind), let geometry = ocrGeometry {
            rects = AnnotationWordSnap.snappedRects(
                drag: box, words: geometry.wordBoxes, lines: geometry.lineBoxes
            )
        } else {
            rects = [box]
        }
        // Coding v1 (Daniel, 2026-08-30, ruling 4): pending tags ride the
        // next highlight-family save — every strip of this ONE gesture.
        let tagKinds: Set<AnnotationKind> = [.highlight, .underline, .strikethrough]
        let tags = tagKinds.contains(kind) ? (windowState?.takePendingMarkupTags() ?? []) : []
        Task {
            var firstSavedId: String?
            for rect in rects {
                let saved = await annotationStore.addNote(
                    scope: .document(documentId),
                    text: "",
                    bbox: rect,
                    kind: kind,
                    color: color,
                    tags: tags
                )
                if firstSavedId == nil { firstSavedId = saved?.id }
            }
            // A NOTE without words is not a note (Daniel, 2026-08-31: "text
            // note doesn't work"). The box is saved — now ask for its text;
            // the markup row's popover commits via `updateText` or deletes
            // the empty annotation on cancel.
            if kind == .note, let firstSavedId {
                NotificationCenter.default.post(
                    name: .previewNoteTextEntry, object: firstSavedId
                )
            }
        }
    }

    // MARK: - Marks over the SELECTION (Daniel, 2026-08-31, rulings 4 & 5)

    /// The boxes the visible selection names: the picked region/word boxes
    /// when `RegionSelection` points at the geometry actually on screen,
    /// else the words the READER's live text selection lit
    /// (`.readerTextSelection` → `linkedSelectionBoxes`). Empty means "no
    /// selection", which is the signal to fall back to the drag/click tools.
    var selectedMarkupBoxes: [OCRGeometryBox] {
        guard let geometry = ocrGeometry, geometryFrameMatchesDisplay(geometry) else { return [] }
        let selection = RegionSelection.shared
        if let artifactId = ocrGeometryArtifactId, selection.artifactId == artifactId,
           !selection.isEmpty {
            let picked = selection.indices
                .filter { geometry.boxes.indices.contains($0) }
                .map { geometry.boxes[$0] }
            if !picked.isEmpty { return picked }
        }
        return linkedSelectionBoxes.map {
            OCRGeometryBox(
                text: "", bbox: $0, level: "word",
                confidence: nil, pageIndex: nil, charStart: nil, charEnd: nil
            )
        }
    }

    /// The selection as one strip per LINE — the shape a highlight or a check
    /// takes over picked words. Same word-snap grammar `promoteSelectedWords`
    /// uses, so a multi-line pick yields per-line bands rather than one
    /// page-blotting union.
    var selectedMarkupStrips: [[Double]] {
        let picked = selectedMarkupBoxes
        guard !picked.isEmpty, let geometry = ocrGeometry else { return [] }
        // Bounded sub-expressions — one chained literal here times the
        // type-checker out (the precedent in +Regions.swift).
        let minX: Double = picked.map { $0.bbox[0] }.min() ?? 0
        let minY: Double = picked.map { $0.bbox[1] }.min() ?? 0
        let maxX: Double = picked.map { $0.bbox[0] + $0.bbox[2] }.max() ?? 0
        let maxY: Double = picked.map { $0.bbox[1] + $0.bbox[3] }.max() ?? 0
        let union: [Double] = [minX, minY, maxX - minX, maxY - minY]
        return AnnotationWordSnap.snappedRects(
            drag: union, words: picked, lines: geometry.lineBoxes
        )
    }

    /// Ruling 5: press Highlight while word boxes are SELECTED and the
    /// selection is painted, in the split button's current color/mode — the
    /// select-words → Highlight path the reader's char-span highlighting
    /// already had. Returns false when nothing is selected, so the caller
    /// falls back to arming the drag.
    @discardableResult
    func highlightSelectedBoxes() -> Bool {
        guard let documentId else { return false }
        let strips = selectedMarkupStrips
        guard !strips.isEmpty else { return false }
        let style = PreviewHighlightStyle(
            rawValue: UserDefaults.standard.string(forKey: PreviewHighlightStyle.storageKey) ?? ""
        )
        // Underline / strikethrough are their OWN kinds, as on the drag path.
        let kind: AnnotationKind = switch style {
        case .underline: .underline
        case .strikethrough: .strikethrough
        default: .highlight
        }
        let color: String? = kind == .highlight ? style?.persistedColor : nil
        let tags = windowState?.takePendingMarkupTags() ?? []
        Task {
            for strip in strips {
                _ = await annotationStore.addNote(
                    scope: .document(documentId), text: "", bbox: strip,
                    kind: kind, color: color, tags: tags
                )
            }
        }
        return true
    }

    /// Ruling 4: a check lands on the text you already picked. Same cycle the
    /// click path runs (none → ✓ → ✓✓ → ✓✓✓ → none, `sameExtent` deciding
    /// what "the same place" means), applied per selected line-strip. Returns
    /// false when nothing is selected, so the tool stays armed for a click.
    @discardableResult
    func checkSelectedBoxes() -> Bool {
        guard let documentId else { return false }
        let strips = selectedMarkupStrips
        guard !strips.isEmpty else { return false }
        let tags = windowState?.takePendingMarkupTags() ?? []
        Task {
            for bbox in strips {
                let existing = annotationStore.annotations.first { annotation in
                    annotation.kind == .rating
                        && (annotation.documentId == documentId || annotation.pageId == documentId)
                        && RegionInteractionLayer.sameExtent(annotation.regionRect, bbox)
                }
                if let existing {
                    let next = (existing.rating ?? 1) + 1
                    _ = await annotationStore.delete(id: existing.id)
                    guard next <= 3 else { continue }  // ✓✓✓ → clear
                    _ = await annotationStore.addNote(
                        scope: .document(documentId), text: "",
                        bbox: bbox, kind: .rating, rating: next
                    )
                } else {
                    _ = await annotationStore.addNote(
                        scope: .document(documentId), text: "",
                        bbox: bbox, kind: .rating, rating: 1, tags: tags
                    )
                }
            }
        }
        return true
    }

    /// Saved annotations for the shown image, as per-kind marks (Daniel,
    /// 2026-08-30: markup should LOOK like what it is). Region-less bookmarks
    /// ride along as whole-page stars.
    var annotationMarks: [AnnotationMark] {
        guard let documentId else { return [] }
        return annotationStore.annotations
            .filter {
                ($0.documentId == documentId || $0.pageId == documentId)
                    && ($0.hasRegion || $0.kind == .bookmark)
            }
            .map(AnnotationMark.init)
    }

    func loadAnnotations() {
        guard let documentId else { return }
        Task { await annotationStore.loadAnnotations(for: .document(documentId), force: true) }
    }
}

#endif
