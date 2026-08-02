import SwiftUI

// MARK: - Sort Field

/// Sortable fields for library documents
enum LibrarySortField: String, CaseIterable, Identifiable {
    case name = "Name"
    case createdAt = "Date Created"
    case updatedAt = "Date Modified"
    /// The historical date the document was WRITTEN (#3322) — the paleography
    /// sort, and the only field in this enum the ENGINE orders. See
    /// `ordersOnServer`.
    case documentDate = "Document Date"
    case fileType = "Type"
    case status = "Status"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .name: return "textformat"
        case .createdAt: return "calendar.badge.plus"
        case .updatedAt: return "calendar.badge.clock"
        case .documentDate: return "calendar"
        case .fileType: return "doc"
        case .status: return "circle.dotted"
        }
    }

    // MARK: - Who owns the ordering

    /// Whether the ENGINE produces the row order for this field.
    ///
    /// Only `documentDate` does, and the reason is that the ordering is not
    /// expressible as a key path. `histdate.document_date_sort_key` returns a
    /// `(jdn, precision_rank)` tuple: ties on the start JDN break precise-first
    /// so a day-precision date sorts ahead of the year that contains it, and a
    /// document with no extracted date falls back to `created_at` CONVERTED TO
    /// A JDN so one integer tuple orders the whole list.
    ///
    /// A client-side `KeyPathComparator` on `dateJdn` would reproduce neither.
    /// It would be a second implementation of the ordering with different
    /// tie-breaking and a different fallback — the two-things-nothing-forces-
    /// to-agree class this whole design exists to avoid.
    var ordersOnServer: Bool {
        self == .documentDate
    }

    /// The `sort_by` value for the listing routes, or nil when the client
    /// orders this field itself. Absent `sort_by` is the pre-existing
    /// behaviour (the stored `sort_order` position), so nil is a real answer
    /// here rather than a missing one.
    var serverSortBy: String? {
        ordersOnServer ? "document_date" : nil
    }

    /// Order rows for display — **the one place the client sort is applied.**
    ///
    /// For a server-ordered field this returns `documents` UNTOUCHED. That is
    /// the entire behaviour, and it is the kind that reads like an oversight:
    /// a `guard` that returns its input looks like a missing implementation,
    /// and re-sorting rows the engine already ordered looks like a fix. It is
    /// not. Applying a comparator on top would silently discard the precision
    /// tie-breaking and the `created_at`-as-JDN fallback described above, and
    /// the list would still look plausible — sorted by *something*, just not
    /// by what the engine decided.
    ///
    /// `LibrarySortFieldServerOrderingTests` fails if this guard is removed.
    static func orderedForDisplay(
        _ documents: [Document],
        field: LibrarySortField,
        using comparators: [KeyPathComparator<Document>]
    ) -> [Document] {
        guard !field.ordersOnServer else { return groupingUndatedLast(documents) }
        return documents.sorted(using: comparators)
    }

    /// Move undated documents to the end, **preserving the engine's relative
    /// order within each group** (#3322).
    ///
    /// This is a stable partition, not a sort — it never compares two
    /// documents, so it cannot introduce a second opinion about ordering. That
    /// distinction is the whole reason it is a separate function from
    /// `orderedForDisplay`: one decides who orders the rows, this one only
    /// decides where the undated ones sit.
    ///
    /// Why it is needed at all: the engine's fallback sorts a document with no
    /// extracted date by its `created_at` converted to a JDN, which is correct
    /// for producing one total order but places undated documents INTERLEAVED
    /// among dated ones — a diary scanned in 2024 landing between two 1791
    /// letters. The fallback stays (it is what makes the ordering total); the
    /// UI just refuses to present the interleaving as though it were evidence.
    ///
    /// The visible order is also the order `filteredDocuments` holds, so
    /// keyboard navigation and the `documentIndexById` prefetch map agree with
    /// what is on screen. A grouping applied only at render time would put
    /// arrow-key order out of step with row order.
    static func groupingUndatedLast(_ documents: [Document]) -> [Document] {
        let dated = documents.filter { $0.dateJdn != nil }
        guard dated.count != documents.count else { return documents }
        return dated + documents.filter { $0.dateJdn == nil }
    }

    func comparator(ascending: Bool) -> [KeyPathComparator<Document>] {
        let order: SortOrder = ascending ? .forward : .reverse
        switch self {
        case .name: return [.init(\.name, order: order)]
        case .createdAt: return [.init(\.createdAt, order: order)]
        case .updatedAt: return [.init(\.updatedAt, order: order)]
        // Header binding only -- `orderedForDisplay` never applies it. The
        // Table needs a comparator its Date column declares so the AppKit
        // sort-descriptor bridge can map the header click back (#4282); the
        // ROWS come from the engine.
        case .documentDate: return [.init(\.dateHeaderSortKey, order: order)]
        case .fileType: return [.init(\.sortableFileType, order: order)]
        case .status: return [.init(\.status.rawValue, order: order)]
        }
    }

    /// Map a comparator key path (as delivered by a Table header click) back to
    /// the sort field it represents, or nil for a key path we never installed.
    /// Total by construction: the setter must treat "unknown key path" as a
    /// no-op — never half-apply (flip direction without a field) — that
    /// inconsistency is the #4282 defect class.
    static func field(forDocumentKeyPath keyPath: PartialKeyPath<Document>) -> LibrarySortField? {
        if keyPath == \Document.name { return .name }
        if keyPath == \Document.createdAt { return .createdAt }
        if keyPath == \Document.updatedAt { return .updatedAt }
        if keyPath == \Document.dateHeaderSortKey { return .documentDate }
        if keyPath == \Document.sortableFileType { return .fileType }
        if keyPath == \Document.status.rawValue { return .status }
        return nil
    }

    /// Same mapping for the outline table's node-typed comparators.
    static func field(
        forOutlineKeyPath keyPath: PartialKeyPath<LibraryOutlineNode>
    ) -> LibrarySortField? {
        if keyPath == \LibraryOutlineNode.document.name { return .name }
        if keyPath == \LibraryOutlineNode.document.createdAt { return .createdAt }
        if keyPath == \LibraryOutlineNode.document.updatedAt { return .updatedAt }
        if keyPath == \LibraryOutlineNode.document.dateHeaderSortKey { return .documentDate }
        if keyPath == \LibraryOutlineNode.document.sortableFileType { return .fileType }
        if keyPath == \LibraryOutlineNode.document.status.rawValue { return .status }
        return nil
    }

    /// The comparator for the outline table's sortable COLUMN backing this
    /// field, or nil when the table exposes no such column (`updatedAt` /
    /// `fileType` are offered by the toolbar sort menu only). The table's
    /// `sortOrder` binding must never carry a comparator that no column
    /// declares: on macOS the Table bridges each comparator to an AppKit
    /// sort descriptor resolved against a column, and a descriptor the
    /// bridge cannot map back is the NSSortDescriptor-bridge crash class
    /// from #4282. Row ORDER is unaffected — rows are pre-sorted upstream
    /// in `recomputeFiltered()`, the binding only drives the header UI.
    func outlineColumnComparator(ascending: Bool) -> KeyPathComparator<LibraryOutlineNode>? {
        let order: SortOrder = ascending ? .forward : .reverse
        switch self {
        case .name: return .init(\.document.name, order: order)
        case .createdAt: return .init(\.document.createdAt, order: order)
        case .status: return .init(\.document.status.rawValue, order: order)
        // The Date column IS sortable, so it must declare a comparator the
        // bridge can resolve (#4282). It drives the header only.
        case .documentDate: return .init(\.document.dateHeaderSortKey, order: order)
        case .updatedAt, .fileType: return nil
        }
    }
}

// MARK: - Sort State Extension

extension LibraryView {

    /// Sync the sortOrder comparator from the raw persisted values
    func syncSortOrder() {
        let field = LibrarySortField(rawValue: sortFieldRaw) ?? .name
        sortOrder = field.comparator(ascending: sortAscending)
    }

    // MARK: - The "No date" section (#3322)

    var activeSortField: LibrarySortField {
        LibrarySortField(rawValue: sortFieldRaw) ?? .name
    }

    /// Whether to split the undated rows into their own section. Both view
    /// modes ask this same question so they cannot disagree about when the
    /// section appears.
    var showsUndatedSection: Bool {
        LibraryDateSectioning.showsUndatedSection(
            sortField: activeSortField,
            documents: filteredDocuments
        )
    }

    var datedDocuments: [Document] {
        LibraryDateSectioning.dated(filteredDocuments) { $0.dateJdn }
    }

    var undatedDocuments: [Document] {
        LibraryDateSectioning.undated(filteredDocuments) { $0.dateJdn }
    }

    var datedOutlineNodes: [LibraryOutlineNode] {
        LibraryDateSectioning.dated(outlineNodes) { $0.document.dateJdn }
    }

    var undatedOutlineNodes: [LibraryOutlineNode] {
        LibraryDateSectioning.undated(outlineNodes) { $0.document.dateJdn }
    }

    /// Tell the store which server ordering the library now wants (#3322).
    ///
    /// Called from every path that can change the active sort, INCLUDING the
    /// folder change — a folder remembers its own sort field, so navigating
    /// from a folder sorted by Date to one sorted by Name changes the request
    /// without the user touching the sort menu.
    ///
    /// The store refetches only if the request actually changed, so calling
    /// this on a Name -> Type change costs nothing.
    func syncServerListingSort() {
        let field = LibrarySortField(rawValue: sortFieldRaw) ?? .name
        let sort = ListingSort.forLibrarySort(field: field, ascending: sortAscending)
        Task { await documentStore.setListingSort(sort) }
    }

    /// Handle a sortOrder change from column-header clicks — syncs sortFieldRaw/sortAscending back.
    /// An unrecognised key path is a full no-op (#4282): the old code fell
    /// through the field mapping but still flipped `sortAscending` and saved,
    /// persisting a direction change for a field it never identified.
    func handleSortOrderChange(_ newOrder: [KeyPathComparator<Document>]) {
        guard let first = newOrder.first,
              let field = LibrarySortField.field(forDocumentKeyPath: first.keyPath) else { return }
        sortFieldRaw = field.rawValue
        sortAscending = first.order == .forward
        saveSortSettings(for: folderId)
    }

    // MARK: - Per-Folder Sort Persistence

    private func sortKey(for id: String?) -> String {
        id ?? "__root__"
    }

    func loadSortSettings(for id: String?) {
        let key = sortKey(for: id)

        if let fieldsData = sortFieldsByFolderJSON.data(using: .utf8),
           let fields = try? JSONDecoder().decode([String: String].self, from: fieldsData),
           let savedField = fields[key] {
            sortFieldRaw = savedField
        } else {
            sortFieldRaw = LibrarySortField.name.rawValue
        }

        if let ascendingData = sortAscendingByFolderJSON.data(using: .utf8),
           let ascendingValues = try? JSONDecoder().decode([String: Bool].self, from: ascendingData),
           let savedAscending = ascendingValues[key] {
            sortAscending = savedAscending
        } else {
            sortAscending = true
        }
    }

    func saveSortSettings(for id: String?) {
        let key = sortKey(for: id)

        var fields: [String: String] = [:]
        if let fieldsData = sortFieldsByFolderJSON.data(using: .utf8),
           let decoded = try? JSONDecoder().decode([String: String].self, from: fieldsData) {
            fields = decoded
        }
        fields[key] = sortFieldRaw
        if let encoded = try? JSONEncoder().encode(fields),
           let json = String(data: encoded, encoding: .utf8) {
            sortFieldsByFolderJSON = json
        }

        var ascendingValues: [String: Bool] = [:]
        if let ascendingData = sortAscendingByFolderJSON.data(using: .utf8),
           let decoded = try? JSONDecoder().decode([String: Bool].self, from: ascendingData) {
            ascendingValues = decoded
        }
        ascendingValues[key] = sortAscending
        if let encoded = try? JSONEncoder().encode(ascendingValues),
           let json = String(data: encoded, encoding: .utf8) {
            sortAscendingByFolderJSON = json
        }
    }
}
