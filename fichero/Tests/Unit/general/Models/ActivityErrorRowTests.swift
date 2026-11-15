//
//  ActivityErrorRowTests.swift
//  FicheroTests
//
//  #6354 `activity.pane.failure-with-its-fix-in-the-row`: a failed row's one button is the engine's primary fix; its words
//  and fix come from the engine's table, never a code.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct ActivityErrorRowTests {
    typealias Phase = ActivityMonitorRow.Phase

    private func failed(_ failure: ActivityJob.Failure?) -> ActivityMonitorRow {
        var job = ActivityJob(id: "j", taskType: "run-a-recipe", name: "Run the recipe", state: .failed, reason: "no credit")
        job.failure = failure
        return ActivityMonitorRow.job(job, libraryId: nil, projectName: nil)
    }

    @Test("a credit failure's button is Settings…, a cap pause's is Continue, a plain failure's is Retry")
    func primaryFix() {
        let credit = ActivityJob.Failure(kind: "no-credit", words: "OpenRouter has no credit left.", fix: "Add credit at OpenRouter.",
                                         actions: ["open-settings", "choose-model", "retry"])
        #expect(failed(credit).paneButton == .settings)
        let cap = ActivityJob.Failure(kind: "cap-refused", words: "A cloud spend cap stopped this run.", fix: "Raise the cap.",
                                      actions: ["resume"])
        #expect(failed(cap).paneButton == .verb(.resume))
        #expect(failed(nil).paneButton == .verb(.retry))
        // Decision 28 (#6588): a kept export paused for its gone folder offers Choose Folder… for that export.
        var gone = ActivityJob.Failure(kind: "export-folder-gone", words: "The folder this export writes to is gone.",
                                       fix: "Reconnect the drive, or choose the export's folder again.",
                                       actions: ["choose-folder", "resume"])
        gone.folderFor = "e1"
        #expect(failed(gone).paneButton == .chooseFolder(export: "e1"))
        #expect(ActivityPaneButton.chooseFolder(export: "e1").title == "Choose Folder…")
    }

    @Test("every action id in the engine's table maps to a word; one the row cannot do, or does not know, is Show Details")
    func everyActionHasAWord() {
        // `llm/failure.ActionKind`, the engine's table.
        let engine = ["retry", "resume", "open-settings", "choose-model", "report-bug", "reconnect", "raise-to", "allow-everywhere",
                      "allow-project", "allow-once", "over-cap-once", "choose-folder"]
        let row = failed(nil)
        for action in engine {
            let title = ActivityPaneButton.forAction(action, row: row)?.title ?? ""
            #expect(title.isEmpty == false, "\(action) has a word")
        }
        #expect(ActivityPaneButton.forAction("report-bug", row: row) == .showDetails)
        #expect(ActivityPaneButton.forAction("something-new", row: row)?.title == "Show Details", "never a gear")
        #expect(ActivityPaneButton.forAction("choose-folder", row: row) == .showDetails, "no export named: the Inspector says")
    }

    @Test("the row carries the fix sentence and never a status code")
    func fixInTheRow() {
        let row = failed(ActivityJob.Failure(kind: "rate-limited", words: "OpenRouter is limiting how fast Fichero can send.",
                                             fix: "Wait a few minutes, then continue the run.", actions: ["resume", "retry"]))
        #expect(row.failure?.fix == "Wait a few minutes, then continue the run.")
        #expect(!(row.failure?.words.contains("429") ?? true))
    }

    @Test("the row's reason is the failure kind's row words when the engine sends them, else the engine's reason")
    func rowWords() {
        var job = ActivityJob(id: "j", taskType: "run-a-recipe", name: "Run", state: .failed, reason: "a long stored sentence.")
        #expect(ActivityMonitorRow.job(job, libraryId: nil, projectName: nil).reason == "a long stored sentence.")
        job.failure = ActivityJob.Failure(kind: "no-credit", words: "OpenRouter has no credit left.", fix: "Add credit.",
                                          actions: ["open-settings"], rowWords: "Out of credit at OpenRouter")
        #expect(ActivityMonitorRow.job(job, libraryId: nil, projectName: nil).reason == "Out of credit at OpenRouter")
    }

    /// #6588: a failed run is listed from the runs list without the engine's failure; its twin in the jobs list has it.
    @Test("a failed run row takes its failure from its job twin: its row words and its Retry")
    func runRowTakesItsJobsFailure() {
        var run = ActivityPaneFixture.row("thread-1", .failed, kind: .run)
        run.reason = "Interrupted: the project was closed at 22:58, before this run finished"
        var job = ActivityJob(id: "thread-1", taskType: "workflow", name: "Detect", state: .failed, reason: run.reason)
        job.failure = ActivityJob.Failure(kind: "interrupted", words: "The run stopped before it finished.",
                                          fix: "Run it again.", actions: ["retry"], rowWords: "Stopped before it finished")
        let row = ActivityPane.withRunFailures([run], jobs: [job]).first
        #expect(row?.failure?.kind == "interrupted")
        #expect(row?.reason == "Stopped before it finished")
        #expect(row.map(ActivityPane.stateLine) == "Stopped before it finished", "the row says why in its eight words")
    }
}
