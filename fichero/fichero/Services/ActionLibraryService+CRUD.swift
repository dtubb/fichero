import FicheroAPIClient
import Foundation
import OSLog

extension ActionLibraryService {
    // MARK: - CRUD

    /// Get action by ID
    func getAction(_ actionId: String) async -> ActionItem? {
        do {
            let response = try await client.api.getActionApiActionsActionIdGet(
                path: .init(actionId: actionId),
            )
            switch response {
            case .ok(let okResponse):
                return try decodeModel(from: try okResponse.body.json, as: ActionItem.self)
            case .unprocessableContent, .undocumented:
                return nil
            }
        } catch {
            if error.isCancellationError { return nil }   // superseded — not a failure
            logger.error("Failed to get action: \(error.localizedDescription)")
            return nil
        }
    }

    /// Delete an action
    func deleteAction(_ actionId: String) async throws {
        let response = try await client.api.deleteActionApiActionsActionIdDelete(
            path: .init(actionId: actionId),
        )
        switch response {
        case .ok:
            logger.info("Deleted action: \(actionId)")
        case .undocumented(let statusCode, _):
            if statusCode == 403 {
                throw ActionLibraryError.cannotDeleteBuiltin
            }
            throw ActionLibraryError.serverError
        case .unprocessableContent:
            throw ActionLibraryError.serverError
        }
    }
}
