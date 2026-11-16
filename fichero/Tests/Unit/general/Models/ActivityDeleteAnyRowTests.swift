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

    @Test("every run and job row is deletable (a running one by Stop then Delete); a step or a page goes with its run")
    func jobRowsAreDeletable() {
        #expect(ActivityPaneVerb.delete.allows(row("done", .done, kind: .job, jobId: "j1")))
        #expect(ActivityPaneVerb.delete.allows(row("failed", .failed, kind: .job, jobId: "j2")))
        #expect(ActivityPaneVerb.delete.allows(row("paused", .paused, kind: .job, jobId: "j3")))
        #expect(ActivityPaneVerb.delete.allows(row("queued", .waiting, kind: .job, jobId: "waiting:thumbnail")))
        #expect(ActivityPaneVerb.delete.allows(row("running", .running, kind: .job, jobId: "j4")))
        #expect(ActivityPaneVerb.deleteNeedsConfirmation([row("running", .running, kind: .job, jobId: "j4")]))
        #expect(!ActivityPaneVerb.deleteNeedsConfirmation([row("paused", .paused, kind: .job, jobId: "j3")]))
        #expect(!ActivityPaneVerb.delete.allows(row("step", .failed, kind: .step, jobId: "s")))
        #expect(!ActivityPaneVerb.delete.allows(row("page", .failed, kind: .page, jobId: "p")))
        #expect(ActivityPaneVerb.delete.allows(row("run", .failed, kind: .run, jobId: nil)))
        #expect(ActivityPaneVerb.delete.allows(row("live-run", .running, kind: .run, jobId: nil)))
    }

    @Test("Archive takes only ended rows; an archived row offers Put Back, not Archive; a waiting or paused row neither")
    func archivable() {
        #expect(ActivityPaneVerb.archive.allows(row("done", .done, kind: .job, jobId: "j1")))
        #expect(ActivityPaneVerb.archive.allows(row("failed", .failed, kind: .run, jobId: nil)),
                "a run takes the engine's run archive, never the runs delete")
        #expect(ActivityPaneVerb.archive.allows(row("stopped", .cancelled, kind: .job, jobId: "j2")))
        #expect(!ActivityPaneVerb.archive.allows(row("paused", .paused, kind: .job, jobId: "j3")))
        #expect(!ActivityPaneVerb.archive.allows(row("queued", .waiting, kind: .job, jobId: "j4")))
        #expect(!ActivityPaneVerb.archive.allows(row("running", .running, kind: .job, jobId: "j5")))
        var archived = row("archived", .done, kind: .job, jobId: "j6")
        archived.isArchived = true
        #expect(!ActivityPaneVerb.archive.allows(archived), "already archived: Put Back is its verb")
        #expect(ActivityPaneVerb.putBack.allows(archived))
    }

    @Test("Delete sends each project's job rows to that project's jobs delete, a kind's row by its own id")
    func jobIdsGoToTheirProject() {
        let one = UUID(), two = UUID()
        let ids = ActivityPaneView.jobIdsByLibrary([
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
