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
            isDrawingRegion = false
            createAnnotation(box: nil, tool: .bookmark)
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
            for rect in rects {
                _ = await annotationStore.addNote(
                    scope: .document(documentId),
                    text: "",
                    bbox: rect,
                    kind: kind,
                    color: color,
                    tags: tags
                )
            }
        }
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
