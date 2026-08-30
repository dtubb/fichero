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
        case .highlight, .note:
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
            case .highlight: return .highlight
            case .note: return .note
            case .bookmark: return .bookmark
            }
        }()
        isDrawingRegion = false
        // The highlight split-button's color rides the saved highlight
        // (Daniel, 2026-08-29). Underline/strikethrough save uncolored until
        // a backing kind exists (see the toolbars design report).
        let color: String? = kind == .highlight
            ? PreviewHighlightStyle(
                rawValue: UserDefaults.standard.string(forKey: PreviewHighlightStyle.storageKey) ?? ""
            )?.persistedColor
            : nil
        Task {
            _ = await annotationStore.addNote(
                scope: .document(documentId),
                text: "",
                bbox: box,
                kind: kind,
                color: color
            )
        }
    }

    /// Saved region boxes (normalized `[x,y,w,h]`) for the shown image.
    var regionBoxes: [[Double]] {
        guard let documentId else { return [] }
        return annotationStore.annotations
            .filter { ($0.documentId == documentId || $0.pageId == documentId) && $0.hasRegion }
            .compactMap(\.regionRect)
    }

    func loadAnnotations() {
        guard let documentId else { return }
        Task { await annotationStore.loadAnnotations(for: .document(documentId), force: true) }
    }
}

#endif
