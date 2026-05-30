import Foundation

struct FolderViewInfo: Codable, Hashable, Identifiable {
    let id: String
    let label: String
    let populated: Bool
    let itemCount: Int

    enum CodingKeys: String, CodingKey {
        case id
        case label
        case populated
        case itemCount = "item_count"
    }
}

struct FolderViewsResponse: Codable, Hashable {
    let folderId: String
    let isWorkspace: Bool
    let curatedItemCount: Int
    let childCount: Int
    let views: [FolderViewInfo]

    enum CodingKeys: String, CodingKey {
        case folderId = "folder_id"
        case isWorkspace = "is_workspace"
        case curatedItemCount = "curated_item_count"
        case childCount = "child_count"
        case views
    }
}

@MainActor
final class FolderService {
    private let apiClient: APIClient

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    func availableViews(folderId: String) async throws -> FolderViewsResponse {
        try await apiClient.get("/folders/\(folderId)/views")
    }
}
