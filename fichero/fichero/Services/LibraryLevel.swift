import Foundation

/// Which tier of the node tree the library grid shows (2026-08-22).
///
/// A diary folder holds two kinds of thing at once, both correctly: OPENINGS —
/// spreads whose two pages moved beneath them — and WHOLE PAGES that were
/// never split. "The folder's children" is therefore an ambiguous question,
/// and only the person looking knows which they meant. Daniel: "I want to be
/// able to show spreads, or show single pages."
///
/// Mirrors `ListingSort`: a small value the store holds, sent to the engine,
/// which owns the actual resolution. The client never derives the tier itself
/// — the engine resolves it through the `prefer_children_in_library` prototype
/// attribute, and a second implementation here would be free to disagree with
/// it. That disagreement is exactly what produced Marshall v3's state, where
/// the library showed spreads, the user selected what the library showed, and
/// every diary entry was extracted from a spread transcript.
enum LibraryLevel: String, CaseIterable, Identifiable, Sendable {
    /// The tree as held: openings AND whole pages side by side.
    case stored
    /// The content tier: openings resolve to their pages; a page that was
    /// never split passes through unchanged.
    case content

    var id: String { rawValue }

    /// What the toggle says. Deliberately the reader's words, not the
    /// model's — someone browsing a diary thinks in spreads and pages, not in
    /// container nodes.
    var title: String {
        switch self {
        case .stored: return "Spreads"
        case .content: return "Pages"
        }
    }

    var systemImage: String {
        switch self {
        case .stored: return "book.pages"
        case .content: return "doc"
        }
    }

    var help: String {
        switch self {
        case .stored:
            return "Show each photographed spread as one item"
        case .content:
            return "Show individual pages, splitting spreads into their pages"
        }
    }

    /// The value sent to the engine. Kept explicit rather than reusing
    /// `rawValue` implicitly, so renaming a case for the UI cannot silently
    /// change the wire contract.
    var wireValue: String {
        switch self {
        case .stored: return "stored"
        case .content: return "content"
        }
    }

    /// What the grid opens on.
    ///
    /// `content`, and the asymmetry of the two failure modes is the reason. A
    /// 1926 diary folder holds 75 openings: at `stored` the reader sees 75
    /// spreads and cannot reach an individual page without drilling into each
    /// one, which is what was reported as broken. At `content` they see the
    /// 150 pages plus the 4 that were never split, and one click gets them
    /// back to spreads when they want the physical object.
    ///
    /// Wrong-but-one-click-away beats right-but-unreachable.
    static let gridDefault: LibraryLevel = .content

    /// What the SIDEBAR uses — always `stored`, and not configurable.
    ///
    /// The sidebar's job is structure. An opening is a real node with real
    /// children, and flattening it would make the hierarchy invisible in the
    /// one surface built to show it: you could never navigate TO a spread,
    /// only to its pages, and the parent/child relationship would vanish from
    /// the tree that exists to display relationships.
    static let sidebar: LibraryLevel = .stored
}
