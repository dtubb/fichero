import FicheroAPIClient
import Foundation

extension ActivityStore {
    /// Most dots one read asks for (the engine's own cap is 2000).
    static let pageGridLimit = 2000

    /// Where a run's dots for one stage (nil: the worst across stages) are kept.
    static func pageGridKey(jobId: String, stage: String?) -> String { stage.map { "\(jobId)|\($0)" } ?? jobId }

    /// Read a run's page states for one stage (`GET /api/activity/jobs/{id}/pages`). A failed read keeps the dots already
    /// shown.
    func loadPageGrid(jobId: String, stage: String? = nil) async {
        do {
            let response = try await activityService.client.api.getRunPageStatesApiActivityJobsJobIdPagesGet(
                path: .init(jobId: jobId), query: .init(stage: stage, offset: 0, limit: Self.pageGridLimit))
            guard case .ok(let ok) = response else { return }
            let grid = ActivityPageGrid(try ok.body.json)
            let key = Self.pageGridKey(jobId: jobId, stage: stage)
            if pageGrids[key] != grid { pageGrids[key] = grid }
        } catch {
            if error.isCancellationError { return }
            log.debug("ActivityStore: pages of \(jobId, privacy: .public) failed \(error.localizedDescription, privacy: .public)")
        }
    }
}
