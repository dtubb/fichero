import Foundation
import OSLog

extension ActivityStore {
    /// Read what a workflow run made (`GET /api/artifacts/?run_id=`), up to `ActivityDetails.madeShown` of them and the
    /// count; the details call it when the run's row changes. A failed read keeps the list already shown.
    func loadRunMade(threadId: String) async {
        do {
            let page = try await ArtifactService(ficheroClient: activityService.client)
                .getAllArtifacts(runId: threadId, limit: ActivityDetails.madeShown)
            if runMade[threadId] != page { runMade[threadId] = page }
        } catch {
            log.debug("ActivityStore: artifacts of \(threadId, privacy: .public) failed \(error.localizedDescription, privacy: .public)")
        }
    }
}
