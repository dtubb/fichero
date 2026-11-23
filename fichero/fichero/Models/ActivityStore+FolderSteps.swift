import Foundation
import OSLog

extension ActivityStore {
    /// A run this session never polled still marks its folders (`activity.run.folder-steps-done`): when the library opens,
    /// the newest of the project's recipe runs (the list's first) is folded into `recipeFolderSteps`, from the list item
    /// when it carries `folder_steps`, else from that run's own status. Older runs are not folded; a failed read keeps
    /// what is shown.
    func foldNewestRunFolderSteps(from runs: [Components.Schemas.RecipeRunStatus]) async {
        guard let newest = runs.first else { return }
        var status = newest
        if newest.folderSteps == nil {
            do {
                guard let read = try await activityService.getRecipeRunStatus(jobId: newest.jobId) else { return }
                status = read
            } catch {
                let why = error.localizedDescription
                log.debug("ActivityStore: folder steps of \(newest.jobId, privacy: .public) failed \(why, privacy: .public)")
                return
            }
        }
        for (folder, steps) in RecipeFolderSteps.byFolder(status) where recipeFolderSteps[folder] != steps {
            recipeFolderSteps[folder] = steps
        }
    }
}
