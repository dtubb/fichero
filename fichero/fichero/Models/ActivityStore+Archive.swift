//
//  ActivityStore+Archive.swift
//  Fichero
//
//  Archive, Show Archived and Put Back (`activity.pane.archive-old-runs`, #6583): the engine's `job.archive` /
//  `job.unarchive`, the archived list read on request.
//

import Foundation

extension ActivityStore {
    /// Archive job rows of their own (`activity.pane.archive-old-runs`, #6583): the engine's `job.archive`; each archived
    /// row leaves `backgroundJobs` in place and is kept for Show Archived and Put Back. Skipped ids (still going) are returned.
    @discardableResult
    func archiveJobs(ids: [String], states: [String]? = nil) async -> RunDeleteOutcome {
        do {
            let answer = try await activityService.archiveJobs(ids: ids, states: states)
            let gone = Set(answer.deletedIds)
            backgroundJobs.removeAll { gone.contains($0.id) }
            return RunDeleteOutcome(deletedIds: answer.deletedIds, skippedIds: answer.skippedIds)
        } catch {
            log.error("ActivityStore: archiveJobs failed \(error.localizedDescription, privacy: .public)")
            return RunDeleteOutcome(deletedIds: [], skippedIds: ids, failure: error.localizedDescription)
        }
    }

    /// Show Archived: the archived rows of this project, read once per request (`activity.pane.archive-old-runs`).
    func refreshArchivedJobs() async {
        do {
            archivedJobs = try await activityService.getBackgroundJobs(archived: true).jobs
        } catch {
            log.error("ActivityStore: archived jobs read failed \(error.localizedDescription, privacy: .public)")
        }
    }
}

/// What a job verb a person started did: how many rows it reached, how many it skipped, and the failure in words.
struct ActivityJobsOutcome: Equatable {
    var done = 0
    var skipped = 0
    var failure: String?
}

/// The parameters `job.delete`, `job.archive` and `job.unarchive` share: the rows, and Stop then Delete for a running one.
struct ActivityJobIdsParams: Encodable, Equatable {
    let ids: [String]
    var stopRunning: Bool?

    enum CodingKeys: String, CodingKey { case ids, stopRunning = "stop_running" }
}

extension ActivityStore {
    /// Delete, Archive and Put Back as a person's change in a window (`undo.one-path`, #6583): the audited `job.delete` /
    /// `job.archive` / `job.unarchive` through the actions route, its row one step on the window's stack, so Edit › Undo
    /// takes it back through the engine's inverse (`job.undelete`, `job.unarchive`, `job.archive`). The jobs list, and
    /// the archived one, are read again after it and after each undo and redo.
    func performUndoable(_ action: String, ids: [String], stopRunning: Bool = false, named: String,
                         actions: ActionsService, steps: WindowSteps?) async -> ActivityJobsOutcome {
        let params = ActivityJobIdsParams(ids: ids, stopRunning: stopRunning ? true : nil)
        do {
            let result = try await AuditedAction.run(
                action, params: params, actionName: named, actionsService: actions, steps: steps,
                afterChange: { [weak self] in
                    guard let self else { return }
                    await refreshBackgroundJobs()
                    if !archivedJobs.isEmpty || action != "job.delete" { await refreshArchivedJobs() }
                    refreshToken += 1
                })
            let counts = result.resultListCounts
            return ActivityJobsOutcome(done: counts["deleted_ids"] ?? counts["archived_ids"] ?? counts["ids"] ?? 0,
                                       skipped: counts["skipped_ids"] ?? 0)
        } catch {
            log.error("ActivityStore: \(action, privacy: .public) failed \(error.localizedDescription, privacy: .public)")
            return ActivityJobsOutcome(skipped: ids.count, failure: error.localizedDescription)
        }
    }
}
