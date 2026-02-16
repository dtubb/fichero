import Foundation

// MARK: - Response Models
// These types are shared across the app for saved search functionality

struct SavedSearchAPI: Codable, Identifiable {
    let id: String
    let query: String
    let isSmartSearch: Bool
    let filters: [String: String]?
    let searchType: String
    let sortBy: String
    let sortDirection: String  // "asc" or "desc"
    let folderPath: String
    let sortOrder: Int  // Position within folder
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case query
        case isSmartSearch = "is_smart_search"
        case filters
        case searchType = "search_type"
        case sortBy = "sort_by"
        case sortDirection = "sort_direction"
        case folderPath = "folder_path"
        case sortOrder = "sort_order"
        case createdAt = "created_at"
    }
}
