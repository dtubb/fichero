import FicheroAPIClient
import Foundation

extension ActivityStore {
    /// Most failed pages one read asks for (the engine's own cap is 2000).
    static let failedPagesLimit = 2000

    /// The rows of one paged read, each page with its one reason; a page the engine gave no reason for says it failed.
    static func failedRows(_ list: Components.Schemas.RunPageStates) -> [ActivityDetails.FailedPageRow] {
        (list.items ?? []).map { ActivityDetails.FailedPageRow(id: $0.documentId, title: $0.name, reason: $0.reason ?? "Failed") }
    }

    /// Read every failed page of a run (`GET /api/activity/jobs/{id}/failed-pages`, `activity.run.failed-pages-paged`, #5960): the
    /// account lists the first ten, this is the rest. A failed read keeps what is shown.
    func loadFailedPages(jobId: String) async {
        do {
            let response = try await activityService.client.api.getRunFailedPagesApiActivityJobsJobIdFailedPagesGet(
                path: .init(jobId: jobId), query: .init(offset: 0, limit: Self.failedPagesLimit))
            guard case .ok(let answer) = response else { return }
            failedPageLists[jobId] = Self.failedRows(try answer.body.json)
        } catch {
            if error.isCancellationError { return }
            log.debug("ActivityStore: failed pages of \(jobId, privacy: .public) failed \(error.localizedDescription, privacy: .public)")
        }
    }
}
