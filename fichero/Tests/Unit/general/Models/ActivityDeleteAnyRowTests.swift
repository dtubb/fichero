//
//  ActivityDeleteAnyRowTests.swift
//  FicheroTests
//
//  #6583: Delete acts on every row the window lists, not only on workflow runs. Spec:
//  `docs/contributor_manual/specs/ui/activity-and-automatic-work.md`, `activity.window.delete-any-row`.
//  WHY (owner 2026-11-13): a failed recipe run, a paused download or a queued group of thumbnails could not be deleted.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct ActivityDeleteAnyRowTests {
    typealias Phase = ActivityMonitorRow.Phase

    private func row(_ id: String, _ phase: Phase, kind: ActivityMonitorRow.Kind, jobId: String?,
                     library: UUID? = nil) -> ActivityMonitorRow {
        ActivityMonitorRow(
            id: id, kind: kind, libraryId: library, runRowID: nil, runThreadId: nil, jobId: jobId, name: id,
            projectName: nil, phase: phase, reason: nil, workingOn: nil, done: 0, total: 0, started: nil, seconds: nil,
            costUsd: nil, tokens: 0, errors: 0, model: nil, isLive: phase.isLive, children: nil, account: nil
        )
    }

    @Test("a finished, failed, paused or queued job row and a kind's row are deletable; a running one and a step are not")
    func jobRowsAreDeletable() {
        #expect(ActivityGroupsView.isDeletable(row("done", .done, kind: .job, jobId: "j1")))
        #expect(ActivityGroupsView.isDeletable(row("failed", .failed, kind: .job, jobId: "j2")))
        #expect(ActivityGroupsView.isDeletable(row("paused", .paused, kind: .job, jobId: "j3")))
        #expect(ActivityGroupsView.isDeletable(row("queued", .waiting, kind: .job, jobId: "waiting:thumbnail")))
        #expect(!ActivityGroupsView.isDeletable(row("running", .running, kind: .job, jobId: "j4")))
        #expect(!ActivityGroupsView.isDeletable(row("step", .failed, kind: .step, jobId: "s")))
        #expect(!ActivityGroupsView.isDeletable(row("page", .failed, kind: .page, jobId: "p")))
        #expect(ActivityGroupsView.isDeletable(row("run", .failed, kind: .run, jobId: nil)))
        #expect(!ActivityGroupsView.isDeletable(row("live-run", .running, kind: .run, jobId: nil)))
    }

    @Test("Archive takes only ended rows; an archived row offers Put Back, not Archive; a waiting or paused row neither")
    func archivable() {
        #expect(ActivityGroupsView.isArchivable(row("done", .done, kind: .job, jobId: "j1")))
        #expect(ActivityGroupsView.isArchivable(row("failed", .failed, kind: .run, jobId: nil)))
        #expect(ActivityGroupsView.isArchivable(row("stopped", .cancelled, kind: .job, jobId: "j2")))
        #expect(!ActivityGroupsView.isArchivable(row("paused", .paused, kind: .job, jobId: "j3")))
        #expect(!ActivityGroupsView.isArchivable(row("queued", .waiting, kind: .job, jobId: "j4")))
        #expect(!ActivityGroupsView.isArchivable(row("running", .running, kind: .job, jobId: "j5")))
        var archived = row("archived", .done, kind: .job, jobId: "j6")
        archived.isArchived = true
        #expect(!ActivityGroupsView.isArchivable(archived), "already archived: Put Back is its verb")
    }

    @Test("Delete sends each project's job rows to that project's jobs delete, a kind's row by its own id")
    func jobIdsGoToTheirProject() {
        let one = UUID(), two = UUID()
        let ids = ActivityMonitorWindow.jobIdsByLibrary([
            row("a", .failed, kind: .job, jobId: "recipe-1", library: one),
            row("b", .waiting, kind: .job, jobId: "waiting:thumbnail", library: one),
            row("c", .done, kind: .job, jobId: "try-9", library: two),
            row("r", .failed, kind: .run, jobId: nil, library: one),  // a run row goes to the runs delete, not here
            row("n", .failed, kind: .job, jobId: "orphan", library: nil)  // no project: nothing to send it to
        ])
        #expect(ids[one] == ["recipe-1", "waiting:thumbnail"])
        #expect(ids[two] == ["try-9"])
        #expect(ids.count == 2)
    }
}
