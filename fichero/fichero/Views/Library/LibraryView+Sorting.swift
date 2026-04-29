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
