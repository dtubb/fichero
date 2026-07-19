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

    var id: String { rawValue }

    /// SF Symbol — mirrors `AnnotationKind.icon` so the reader and inspector agree.
    var icon: String {
        switch self {
        case .highlight: return "highlighter"
        case .note: return "note.text"
        case .bookmark: return "bookmark"
        }
    }

    var label: String {
        switch self {
        case .highlight: return "Highlight"
        case .note: return "Add Note"
        case .bookmark: return "Bookmark"
        }
    }
}

// MARK: - Page navigation descriptor

/// Page-within-document navigation state for the reader toolbar. Supplied by the
/// PDF reader; `nil` (or a single-page document) greys the nav controls out.
struct ReaderPageNav {
    let pageIndex: Int
    let pageCount: Int
    let canGoPrevious: Bool
    let canGoNext: Bool
    let goPrevious: () -> Void
    let goNext: () -> Void
}
