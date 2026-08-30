import SwiftUI

// MARK: - Reader annotation tools

/// The annotation tools surfaced by the unified reader toolbar.
///
/// The toolbar only *emits* the requested tool to its host via `onAnnotate`.
/// Region-anchored creation (drawing a highlight box / dropping a pin) and
/// on-canvas rendering of saved annotations are owned by **#2458**; until that
/// lands, hosts wire these to a clearly-marked stub. The page-scoped note path
/// (`AnnotationStore.addNote`) already exists in the backend.
enum ReaderAnnotationTool: String, CaseIterable, Identifiable {
    case highlight
    case note
    case bookmark
    /// The annotation bar's line tool (Daniel, 2026-08-30) — drag a stroke,
    /// saved as the `line` kind with the dragged rect as its extent.
    case line

    var id: String { rawValue }

    /// SF Symbol — mirrors `AnnotationKind.icon` so the reader and inspector agree.
    var icon: String {
        switch self {
        case .highlight: return "highlighter"
        case .note: return "note.text"
        case .bookmark: return "bookmark"
        case .line: return "line.diagonal"
        }
    }

    var label: String {
        switch self {
        case .highlight: return "Highlight"
        case .note: return "Add Note"
        case .bookmark: return "Bookmark"
        case .line: return "Line"
        }
    }
}

// MARK: - Page navigation descriptor

/// Page-within-document navigation state for the reader toolbar. Supplied by the
/// PDF reader; `nil` (or a single-page document) greys the nav controls out.
/// Which rendition of the current page is showing, and how to step between
/// them (2026-08-20 bbox review).
///
/// Renditions are alternative PIXELS of one page — the archival original, a
/// contrast-enhanced pass, a background-removed copy. Stepping between them is
/// a different axis from turning pages: pages change WHAT you are reading,
/// renditions change how the same thing looks.
///
/// `name` is shown, always, whenever more than one exists. A reader who cannot
/// tell they are looking at an enhanced crop cannot judge what they are
/// seeing — which is precisely how a corpus-wide mis-registration stayed
/// invisible for months.
struct ReaderRenditionNav {
    let name: String
    let index: Int
    let count: Int
    /// True when this rendition is not in the page's own frame (cropped,
    /// rotated, deskewed) — so the image shape changes on the flip, and boxes
    /// anchored to the page frame do not apply to it unchanged.
    let hasOwnFrame: Bool
    /// Stepping actions, or `nil` while flipping is not yet possible.
    ///
    /// Switching the displayed rendition requires fetching THAT rendition's
    /// bytes, and no endpoint serves them yet (`getSourceData` returns the
    /// document's source, not a named rendition). Until one exists the chrome
    /// shows WHICH rendition is displayed and how many there are — which is
    /// the part that makes the view honest — and draws no chevrons at all.
    /// A visible control that does nothing is worse than an absent one.
    let goPrevious: (() -> Void)?
    let goNext: (() -> Void)?
}

struct ReaderPageNav {
    let pageIndex: Int
    let pageCount: Int
    let canGoPrevious: Bool
    let canGoNext: Bool
    let goPrevious: () -> Void
    let goNext: () -> Void
}
