//
//  ActivityStore+Archive.swift
//  Fichero
//
//  Archive, Show Archived and Put Back (`activity.pane.archive-old-runs`, #6583): the engine's `job.archive` /
//  `job.unarchive`, the archived list read on request.
//

import Foundation

extension ActivityStore {
    /// Undo of Delete (`activity.pane.archive-old-runs`): the deleted rows come back as they were; the next poll lists them.
    @discardableResult
    func undeleteJobs(ids: [String]) async -> [String] {
        do {
            return try await activityService.undeleteJobs(ids: ids)
        } catch {
            log.error("ActivityStore: undeleteJobs failed \(error.localizedDescription, privacy: .public)")
            return []
        }
    }

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

    /// Put Back: the archived rows are listed again, unchanged; they leave `archivedJobs` here and the next poll lists them.
    @discardableResult
    func unarchiveJobs(ids: [String]) async -> [String] {
        do {
            let back = Set(try await activityService.unarchiveJobs(ids: ids))
            archivedJobs.removeAll { back.contains($0.id) }
            return Array(back)
        } catch {
            log.error("ActivityStore: unarchiveJobs failed \(error.localizedDescription, privacy: .public)")
            return []
        }
    }
}
