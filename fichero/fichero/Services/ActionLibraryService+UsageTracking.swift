import Foundation
import OSLog

extension ActionLibraryService {
    // MARK: - Usage Tracking

    /// Record that an action was used
    func recordUse(_ actionId: String) async {
        do {
            _ = try await client.api.recordActionUseApiActionsActionIdUsePost(
                path: .init(actionId: actionId),
            )
            logger.debug("Recorded use of action: \(actionId)")
        } catch {
            logger.error("Failed to record action use: \(error.localizedDescription)")
        }
    }
}
