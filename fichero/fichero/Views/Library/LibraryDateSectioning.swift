import Foundation

/// The "No date" section (#3322 step 6).
///
/// One source for the predicate AND the title, consumed by both the outline
/// table and the list. The two view modes render rows completely differently —
/// `Section` inside a `Table`'s row builder versus a header view in a
/// `LazyVStack` — and that is exactly the shape where one grouping quietly
/// becomes two that disagree about when it appears or what it is called.
///
/// The grouping ORDER is not decided here. `LibrarySortField.groupingUndatedLast`
/// already moved the undated rows to the end of `filteredDocuments`, so this
/// only names the boundary that is already there.
enum LibraryDateSectioning {

    /// The heading over the undated rows.
    ///
    /// Deliberately neutral. The four date states stay distinguishable INSIDE
    /// the group — the Date cell renders each row through
    /// `DocumentDateDisplay`, so "Undated in source" (the manuscript says n.d.,
    /// which a historian cites) still reads differently from "Date not
    /// examined" (extraction never ran, which is not evidence at all). A
    /// heading that claimed either would flatten that distinction for every row
    /// beneath it, which is the collapse this whole feature exists to prevent.
    static let undatedSectionTitle = "No date"

    /// Whether the undated rows should be split into their own section.
    ///
    /// Two conditions, and both matter:
    ///
    /// - the active sort must be `documentDate`. Under sort-by-name "undated"
    ///   is not a fact the ordering is about, and a section for it would be
    ///   inventing a hierarchy the user did not ask for;
    /// - something must actually be undated. A "No date" heading over an empty
    ///   group, or a lone unlabelled section containing everything, is chrome
    ///   that answers a question nobody asked.
    static func showsUndatedSection(
        sortField: LibrarySortField,
        documents: [Document]
    ) -> Bool {
        guard sortField.ordersOnServer else { return false }
        return documents.contains { $0.dateJdn == nil }
    }

    /// Rows whose historical date is known.
    static func dated<T>(_ items: [T], dateJdn: (T) -> Int?) -> [T] {
        items.filter { dateJdn($0) != nil }
    }

    /// Rows with no extracted date — the section's contents.
    ///
    /// This is `date_jdn == nil`, NOT "the engine had no opinion". The engine
    /// still ordered these by `created_at` converted to a JDN, and that order
    /// is preserved within the group; what the section refuses to do is
    /// interleave them among dated rows, where the fallback would read as a
    /// claim about when the document was written.
    static func undated<T>(_ items: [T], dateJdn: (T) -> Int?) -> [T] {
        items.filter { dateJdn($0) == nil }
    }
}
