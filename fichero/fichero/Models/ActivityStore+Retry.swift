import Foundation

// Retry on a workflow run (#5356, the engine's 47b7a0788): the engine answers a NEW run's id with `replaces` naming
// the old one, which it no longer lists. Activity swaps the old row for the new run in place: one row, and no state
// set on the old id. Pure, so the swap is tested without a store.
extension ActivityStore {
    /// The jobs list with the old run's row turned into the new run's, where it stood, in the state the retry answered.
    static func swapping(_ jobs: [ActivityJob], old: String, new: String, state: String) -> [ActivityJob] {
        guard jobs.contains(where: { $0.id == old }) else { return jobs }
        var swapped: [ActivityJob] = []
        for job in jobs where job.id != new {
            guard job.id == old else {
                swapped.append(job)
                continue
            }
            swapped.append(ActivityJob(
                id: new, taskType: job.taskType, name: job.name, library: job.library, current: 0, total: job.total,
                percent: 0, state: ActivityJob.State(raw: state), reason: nil, parentId: job.parentId,
                offer: nil, runId: job.runId
            ))
        }
        return swapped
    }

    /// The runs with the old run's row turned into the new run's, where it stood.
    static func swapping(_ runs: [ActivityRun], old: String, new: String, state: String) -> [ActivityRun] {
        guard runs.contains(where: { $0.runId == old }) else { return runs }
        var swapped: [ActivityRun] = []
        for run in runs where run.runId != new {
            swapped.append(run.runId == old ? run.retried(as: new, state: state) : run)
        }
        return swapped
    }
}

extension ActivityRun {
    /// This row, now the run that reads its pages again: the new run's ids, waiting or running, no failure.
    func retried(as new: String, state: String) -> ActivityRun {
        let rowId = id.hasSuffix("|\(runId)") ? String(id.dropLast(runId.count)) + new : new
        let status: ActivityRunStatus = ["waiting", "queued", "pending"].contains(state.lowercased())
            ? .running : activityMapRunStatus(state)
        return ActivityRun(
            id: rowId, runId: new, workflowId: workflowId, threadId: new, workflowName: workflowName,
            timestamp: Date(), status: status, progress: nil, currentStep: nil, errorCount: 0, fileCount: fileCount,
            isLive: isLive, libraryId: libraryId, libraryName: libraryName, failureReason: nil
        )
    }
}
