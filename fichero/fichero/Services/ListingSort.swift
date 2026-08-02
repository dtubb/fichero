import Foundation

/// A server-side ordering for the document listing routes (#3322).
///
/// Deliberately a plain pair of already-encoded strings rather than the view's
/// `LibrarySortField`: the service layer talks to the API, and the API's
/// vocabulary is `sort_by` / `sort_direction`. Handing the enum down would put
/// a `Views/` type in a service signature and make the fetch path care which
/// menu item the user picked.
///
/// **Its absence is meaningful.** A nil `ListingSort` means "use the stored
/// sibling order", which is the pre-existing behaviour of both listing routes
/// and the correct request for every field the client orders itself. It is not
/// a missing argument to be filled in with a default.
struct ListingSort: Equatable {
    /// The `sort_by` value — the engine rejects anything it does not implement,
    /// so this is never a free-form string in practice.
    let field: String
    /// `"asc"` or `"desc"`.
    let direction: String

    init(field: String, ascending: Bool) {
        self.field = field
        self.direction = ascending ? "asc" : "desc"
    }

    /// The ordering to request for a library sort field, or nil when the client
    /// orders that field itself.
    ///
    /// One place decides this, so "which fields go to the server" cannot drift
    /// apart from "which fields skip the client sort" — those are the same
    /// question, and answering it twice is how the two get out of step.
    static func forLibrarySort(field: LibrarySortField, ascending: Bool) -> ListingSort? {
        guard let sortBy = field.serverSortBy else { return nil }
        return ListingSort(field: sortBy, ascending: ascending)
    }

    /// Whether moving from `old` to `new` needs the rows fetched again.
    ///
    /// This is decision (a): refetch on ENTERING and LEAVING a server-ordered
    /// sort, not on every sort change. It is expressed as "the request we would
    /// send is different" rather than as "did the user enter or leave Date",
    /// because those are the same condition and the second phrasing invites a
    /// special case per field.
    ///
    /// What falls out of it:
    /// - Name -> Type: both nil, no refetch. Neither field costs a round trip,
    ///   which is the whole reason (b) was rejected — paying uniformly for a
    ///   capability one field uses is a tax, not consistency.
    /// - Name -> Document Date, and back: the request changes, so refetch.
    /// - Ascending -> descending WITHIN Document Date: also a refetch. The
    ///   engine decides direction; reversing the array client-side would flip
    ///   the rows without re-deciding the precision ties, which is the same
    ///   defect as re-sorting, just cheaper-looking.
    static func requiresRefetch(from old: ListingSort?, to new: ListingSort?) -> Bool {
        old != new
    }
}
