import Foundation
import OSLog

extension ActionLibraryService {
    // MARK: - Import/Export

    /// Export action as JSON
    func exportAction(_ actionId: String) async throws -> String {
        let response = try await client.api.exportActionApiActionsActionIdExportGet(
            path: .init(actionId: actionId),
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.jsonData
        case .unprocessableContent, .undocumented:
            throw ActionLibraryError.serverError
        }
    }

    /// Import action from JSON
    func importAction(_ json: String, newId: Bool = true) async throws -> ActionItem {
        let response = try await client.api.importActionApiActionsImportPost(
            body: .json(.init(jsonData: json, newId: newId))
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json, as: ActionItem.self)
        case .unprocessableContent, .undocumented:
            throw ActionLibraryError.serverError
        }
    }
}
