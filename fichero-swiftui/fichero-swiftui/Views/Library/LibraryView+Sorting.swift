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
}

// MARK: - Sort State Extension

extension LibraryView {

    /// Sync the sortOrder comparator from the raw persisted values
    func syncSortOrder() {
        let field = LibrarySortField(rawValue: sortFieldRaw) ?? .name
        sortOrder = field.comparator(ascending: sortAscending)
    }

    /// Handle a sortOrder change from column-header clicks — syncs sortFieldRaw/sortAscending back
    func handleSortOrderChange(_ newOrder: [KeyPathComparator<Document>]) {
        guard let first = newOrder.first else { return }
        let ascending = first.order == .forward
        if first.keyPath == \Document.name {
            sortFieldRaw = LibrarySortField.name.rawValue
        } else if first.keyPath == \Document.createdAt {
            sortFieldRaw = LibrarySortField.createdAt.rawValue
        } else if first.keyPath == \Document.updatedAt {
            sortFieldRaw = LibrarySortField.updatedAt.rawValue
        } else if first.keyPath == \Document.sortableFileType {
            sortFieldRaw = LibrarySortField.fileType.rawValue
        } else if first.keyPath == \Document.status.rawValue {
            sortFieldRaw = LibrarySortField.status.rawValue
        }
        sortAscending = ascending
        saveSortSettings(for: folderId)
    }

    // MARK: - Per-Folder Sort Persistence

    private func sortFieldKey(for id: String?) -> String {
        id.map { "librarySortField_\($0)" } ?? "librarySortField"
    }

    private func sortAscendingKey(for id: String?) -> String {
        id.map { "librarySortAscending_\($0)" } ?? "librarySortAscending"
    }

    func loadSortSettings(for id: String?) {
        let defaults = UserDefaults.standard
        sortFieldRaw = defaults.string(forKey: sortFieldKey(for: id)) ?? LibrarySortField.name.rawValue
        if let saved = defaults.object(forKey: sortAscendingKey(for: id)) as? Bool {
            sortAscending = saved
        } else {
            sortAscending = true
        }
    }

    func saveSortSettings(for id: String?) {
        let defaults = UserDefaults.standard
        defaults.set(sortFieldRaw, forKey: sortFieldKey(for: id))
        defaults.set(sortAscending, forKey: sortAscendingKey(for: id))
    }
}
