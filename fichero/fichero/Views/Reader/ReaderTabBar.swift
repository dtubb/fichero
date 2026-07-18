import SwiftUI

/// The Reader's three top-level tabs — the 2026-07-11 reader IA fold
/// (`docs/superpowers/specs/2026-07-11-reader-ia-design.md`, REVIEWED +
/// APPROVED). The reader collapses ~10 WebKit modes into **Page / Knowledge /
/// Notes**, native chrome over WebKit content, mirroring the Inspector's 10→4
/// fold:
///
/// - **Page** — read the source. Absorbs WebKit-PDF/Document, the transcript,
///   the page image/grid, loupe, page-turn, and image edits.
/// - **Knowledge** — explore what we know. Absorbs Entities, Claims, Graph, KG,
///   plus Timeline & Map (as sub-modes) and Digest + Sources (as a section) —
///   the existing `DocumentKGSurface` / `KGSurfaceTab` surface.
/// - **Notes** — the human reading layer: highlights, notes, bookmarks anchored
///   to the page.
///
/// Preview stays a SEPARATE quick-look surface (Q3) and Canvas/Spatial stay
/// Library view modes — neither folds in here.
enum ReaderTab: String, CaseIterable, Identifiable, SurfaceTab {
    case page
    case knowledge
    case notes

    var id: String { rawValue }

    /// Human-readable label shown on the native top tab.
    var title: String {
        switch self {
        case .page: return "Page"
        case .knowledge: return "Knowledge"
        case .notes: return "Notes"
        }
    }

    /// SF Symbol mirroring the Inspector tab-bar visual language.
    var icon: String {
        switch self {
        case .page: return "doc.text.image"
        case .knowledge: return "point.3.connected.trianglepath.dotted"
        case .notes: return "note.text"
        }
    }

    /// Tooltip: what the tab shows. (Mirrors `KGSurfaceTab.helpText`.)
    var help: String {
        switch self {
        case .page: return "Page — read the source: image, transcript, loupe, page-turn"
        case .knowledge: return "Knowledge — explore entities, claims, graph, timeline, map, and the digest"
        case .notes: return "Notes — your highlights, notes, and bookmarks anchored to the page"
        }
    }
}

/// Notes-tab sub-mode (#3513): the anchored reading marks (highlights / notes /
/// bookmarks) or free-text document notes. Both live under Notes so the reading
/// layer and loose notes share one tab.
enum ReaderNotesMode: String, CaseIterable, Identifiable {
    case annotations
    case notes

    var id: String { rawValue }

    var title: String {
        switch self {
        case .annotations: return "Marks"
        case .notes: return "Notes"
        }
    }

    var icon: String {
        switch self {
        case .annotations: return "highlighter"
        case .notes: return "note.text"
        }
    }

    var help: String {
        switch self {
        case .annotations: return "Highlights, notes, and bookmarks anchored to the page"
        case .notes: return "Free-text notes about this document"
        }
    }
}

// The Reader's top-tab switcher is now the shared `SurfaceTabBar` (#3530) —
// the same icon-button row the Inspector uses — so both surfaces read as one
// system. `ReaderTab` conforms to `SurfaceTab` above; the reader constructs
// `SurfaceTabBar(tabs: ReaderTab.allCases, selection:)` at its call site. The
// bespoke segmented `ReaderTabBar` view was retired in the extraction.
