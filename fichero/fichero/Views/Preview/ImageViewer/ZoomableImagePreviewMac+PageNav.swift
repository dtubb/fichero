#if os(macOS)
import SwiftUI

// MARK: - Page arrows + pan predicates (split from ZoomableImagePreviewMac
// for file_length / type_body_length).

extension ZoomableImagePreview {
    /// Whether the scaled image can travel horizontally in the viewport —
    /// the arrow-key grammar's pan-vs-navigate test (same rule the trackpad
    /// swipe uses in SiblingSwipeScrollView): the scaled width must exceed
    /// the visible width by more than a hairline.
    var canPanHorizontally: Bool {
        // The visible window is NORMALIZED (0-1): seeing less than the full
        // image width means horizontal travel is possible.
        guard geometry.visible.width > 0 else { return false }
        return geometry.visible.width < 0.999
    }

    /// The vertical twin — ↑/↓'s pan-vs-flip-rendition test.
    var canPanVertically: Bool {
        guard geometry.visible.height > 0 else { return false }
        return geometry.visible.height < 0.999
    }

    /// The position to use for magnifier (locked or cursor)
    var magnifierPosition: CGPoint {
        magnifierLocked ? lockedPosition : cursorPosition
    }

    // Unified, persistent reader toolbar (#2423 / #2421) — bottom-anchored.
    // Image capabilities: zoom + magnifier-panel + loupe + image-edit +
    // annotation enabled; page-navigation renders greyed (a single image has no
    // pages). Split buttons are injected by MiniToolbar. Extracted from the body
    // so the (large) image-preview body stays under the type-checker's limit.
    /// Sibling position for the toolbar's page arrows (Daniel, 2026-08-21:
    /// "PDF has page arrows, but images don't — we want them consistent").
    /// The ARROWS step through the same notification the swipe uses, so the
    /// actual navigation stays ContentView's one sibling walk; this only
    /// reports position. Non-folder siblings of the current listing, with the
    /// folder-children fallback the sibling walk itself applies.
    var imagePageNav: ReaderPageNav? {
        guard let documentId, let store = documentStore else { return nil }
        var siblings = store.currentDocuments.filter { $0.docType != .folder }
        if !siblings.contains(where: { $0.id == documentId }),
           let kids = store.childrenCache.values.first(
            where: { $0.contains { $0.id == documentId } }
           ) {
            siblings = kids.filter { $0.docType != .folder }
        }
        guard siblings.count > 1,
              let index = siblings.firstIndex(where: { $0.id == documentId }) else { return nil }
        return ReaderPageNav(
            pageIndex: index,
            pageCount: siblings.count,
            canGoPrevious: index > 0,
            canGoNext: index < siblings.count - 1,
            goPrevious: {
                PreviewSwapAnimation.park(.pageStep(forward: false))
                NotificationCenter.default.post(name: .previewSiblingSwipe, object: -1)
            },
            goNext: {
                PreviewSwapAnimation.park(.pageStep(forward: true))
                NotificationCenter.default.post(name: .previewSiblingSwipe, object: 1)
            }
        )
    }
}
#endif
