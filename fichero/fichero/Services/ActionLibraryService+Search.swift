import FicheroAPIClient
import Foundation
import OSLog

extension ActionLibraryService {
    // MARK: - Search

    /// Search actions
    func search(query: String? = nil, category: String? = nil, tags: [String]? = nil) async -> [ActionItem] {
        do {
            let response = try await client.api.searchActionsApiActionsSearchGet(
                query: .init(
                    query: (query?.isEmpty == false) ? query : nil,
                    category: category,
                    tags: (tags?.isEmpty == false) ? tags?.joined(separator: ",") : nil
                ),
            )
            switch response {
            case .ok(let okResponse):
                return try decodeModels(from: try okResponse.body.json.items, as: ActionItem.self)
            case .unprocessableContent, .undocumented:
                return []
            }
        } catch {
            if error.isCancellationError { return [] }   // superseded — not a failure
            logger.error("Search failed: \(error.localizedDescription)")
            return []
        }
    }
}
