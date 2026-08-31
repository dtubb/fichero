import Foundation

// MARK: - What the listing shows (2026-08-31)

/// The four answers the bottom bar's **Show** control offers: Spreads, Pages,
/// Regions, Extracted Data. Daniel, 2026-08-31: "so the listing can show just
/// pages, just regions".
///
/// Two of the four are a TIER and two are a KIND, and the split is not cosmetic:
///
/// - **Spreads / Pages** are `LibraryLevel` — a question about which tier of the
///   node tree the engine resolves, answered server-side through the
///   `prefer_children_in_library` prototype attribute. The client never derives
///   it (see `LibraryLevel`'s note on why a second implementation here is how
///   Marshall v3 ended up extracting every diary entry from a spread).
/// - **Regions / Extracted Data** are a NARROWING of the content tier the engine
///   already returned. There is no engine parameter for "children that carry a
///   region", so this filters what has loaded — exactly the way the ⌘F filter
///   row narrows the same list — rather than inventing a wire contract the
///   engine does not implement.
///
/// The facts each kind reads are the ones the rest of the app already reads, not
/// new ones invented here: `regionInParent` is what `MultiSelectionReaderView`
/// and the inspector's regions list call a region node, and `nodeKind == "entry"`
/// is what `WorkflowSuggestionPolicy` and the entry editor call an extracted
/// entry (the engine writes it in `diary_entries.py`). Promoted artifacts carry
/// `nodeKind == "artifact"` and are extraction output too, so they join entries
/// rather than falling into a fifth category nobody asked for.
enum LibraryShowKind: String, CaseIterable, Identifiable, Sendable {
    case spreads
    case pages
    case regions
    case extractedData

    var id: String { rawValue }

    /// The engine tier this kind needs underneath it. Regions and entries are
    /// CHILDREN, so both ask for the content tier and then narrow it — asking
    /// for `stored` would hide the very nodes they want to show.
    var level: LibraryLevel {
        switch self {
        case .spreads: return .stored
        case .pages, .regions, .extractedData: return .content
        }
    }

    /// The reader's words, like `LibraryLevel.title` — nobody browsing a diary
    /// thinks in container nodes.
    var title: String {
        switch self {
        case .spreads: return "Spreads"
        case .pages: return "Pages"
        case .regions: return "Regions"
        case .extractedData: return "Extracted Data"
        }
    }

    var systemImage: String {
        switch self {
        case .spreads: return "book.pages"
        case .pages: return "doc"
        case .regions: return "square.dashed"
        case .extractedData: return "tablecells"
        }
    }

    var help: String {
        switch self {
        case .spreads: return "Show each photographed spread as one item"
        case .pages: return "Show individual pages, splitting spreads into their pages"
        case .regions: return "Show only regions cut out of a page"
        case .extractedData: return "Show only extracted entries and artifacts"
        }
    }

    /// Whether this kind narrows client-side at all. Spreads and Pages are
    /// answered entirely by the tier, so they pass every row through.
    var narrowsClientSide: Bool {
        self == .regions || self == .extractedData
    }

    /// Does this document belong in the listing under this kind?
    ///
    /// Containers ALWAYS pass. Narrowing a folder's listing to regions must not
    /// also strip the subfolders you walk through to reach other regions —
    /// hiding the navigation is not filtering the content (Finder principle: a
    /// filter narrows what you are looking at, never how you get anywhere).
    ///
    /// nonisolated + pure so it is testable off-main.
    nonisolated func matches(_ document: Document) -> Bool {
        if document.docType == .folder || document.docType == .group { return true }
        switch self {
        case .spreads, .pages:
            return true
        case .regions:
            // A region node states WHERE it sits on its parent. Entries state
            // that too, so they are excluded here — they have their own kind,
            // and a "Regions" listing that silently included every extracted
            // entry would make the two choices indistinguishable.
            return Self.isRegionNode(document) && !Self.isExtractedNode(document)
        case .extractedData:
            return Self.isExtractedNode(document)
        }
    }

    /// A node cut out of its parent's image. `regionInParent` is the one field
    /// for that fact; `bbox` is the pre-rename column and still populated on
    /// rows written before the migration, so both are read.
    nonisolated static func isRegionNode(_ document: Document) -> Bool {
        if document.regionInParent != nil { return true }
        return (document.bbox?.count ?? 0) == 4
    }

    /// Workflow output promoted to a node: diary entries (`entry`) and promoted
    /// artifacts (`artifact`).
    nonisolated static func isExtractedNode(_ document: Document) -> Bool {
        document.nodeKind == "entry" || document.nodeKind == "artifact"
    }

    /// Storage key for the persisted narrowing. The tier half is NOT stored
    /// here — `DocumentStore.libraryLevel` owns it.
    static let storageKey = "library.showKind"
}
