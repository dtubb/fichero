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
        #expect(failed(credit).oneButton == .fix)
        let cap = ActivityJob.Failure(kind: "cap-refused", words: "A cloud spend cap stopped this run.", fix: "Raise the cap.",
                                      actions: ["resume"])
        #expect(failed(cap).oneButton == .resume)
        #expect(failed(nil).oneButton == .retry)
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
}
