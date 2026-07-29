import SwiftUI

// MARK: - Sort Field

/// Sortable fields for library documents
enum LibrarySortField: String, CaseIterable, Identifiable {
    case name = "Name"
    case createdAt = "Date Created"
    case updatedAt = "Date Modified"
    case fileType = "Type"
    case status = "Status"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .name: return "textformat"
        case .createdAt: return "calendar.badge.plus"
        case .updatedAt: return "calendar.badge.clock"
        case .fileType: return "doc"
        case .status: return "circle.dotted"
        }
    }

    func comparator(ascending: Bool) -> [KeyPathComparator<Document>] {
        let order: SortOrder = ascending ? .forward : .reverse
        switch self {
        case .name: return [.init(\.name, order: order)]
        case .createdAt: return [.init(\.createdAt, order: order)]
        case .updatedAt: return [.init(\.updatedAt, order: order)]
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
