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
enum ReaderTab: String, CaseIterable, Identifiable {
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

/// Page-tab layout (#3502): read the source (image / PDF page) alone, the
/// transcript alone, or the two side by side. "Read the source" is one tab, so
/// image ↔ transcript is a layout toggle inside Page rather than separate modes.
enum ReaderPageLayout: String, CaseIterable, Identifiable {
    case source
    case split
    case transcript

    var id: String { rawValue }

    var title: String {
        switch self {
        case .source: return "Source"
        case .split: return "Split"
        case .transcript: return "Transcript"
        }
    }

    var icon: String {
        switch self {
        case .source: return "photo"
        case .split: return "rectangle.split.2x1"
        case .transcript: return "text.alignleft"
        }
    }

    var help: String {
        switch self {
        case .source: return "Show the page image / source only"
        case .split: return "Show the source and transcript side by side"
        case .transcript: return "Show the transcript only"
        }
    }
}

/// Native top-tab switcher for the Reader. The reader is the center pane with
/// room to spare, and top tabs read well — the DECIDED switcher style (Daniel
/// 2026-07-11): native chrome over the WebKit/native content beneath. A
/// segmented `Picker` is the native, keyboard- and accessibility-friendly
/// top-tab control; it never scrolls with the content (fixed chrome).
struct ReaderTabBar: View {
    @Binding var selection: ReaderTab

    var body: some View {
        Picker("Reader view", selection: $selection) {
            ForEach(ReaderTab.allCases) { tab in
                Label(tab.title, systemImage: tab.icon)
                    .help(tab.help)
                    .tag(tab)
            }
        }
        .pickerStyle(.segmented)
        .labelStyle(.titleAndIcon)
        .accessibilityIdentifier("readerTabBar")
    }
}
