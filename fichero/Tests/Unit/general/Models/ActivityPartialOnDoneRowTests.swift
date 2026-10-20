//
//  ActivityPartialOnDoneRowTests.swift
//  FicheroTests
//
//  #5937: a finished run that lost pages keeps the state `done`; its reason says "Partial: N of M pages read (...)" and the
//  rows show it instead of Done/Completed. Spec: `activity.run.partial-said-on-a-done-row`.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct ActivityPartialOnDoneRowTests {
    private func row(phase: ActivityMonitorRow.Phase, reason: String?) -> ActivityMonitorRow {
        ActivityMonitorRow(
            id: "r", kind: .run, libraryId: nil, runRowID: nil, runThreadId: nil, jobId: "j",
            name: "Transcribe", projectName: nil, phase: phase, reason: reason, workingOn: nil, done: 8,
            total: 10, started: nil, seconds: 5, costUsd: nil, tokens: 0, errors: 0, model: nil,
            isLive: false, children: nil, account: nil
        )
    }

    @Test func aDoneRowWithAPartialReasonShowsIt() {
        let words = "Partial: 8 of 10 pages read (2 stopped)"
        #expect(row(phase: .done, reason: words).stateText == words)
        #expect(ActivityMonitorRow.partialWords(words) == words)
    }

    @Test func aPlainDoneRowStaysDone() {
        #expect(row(phase: .done, reason: nil).stateText == "Done")
        #expect(row(phase: .done, reason: "Done: 3 steps run").stateText == "Done")
        #expect(ActivityMonitorRow.partialWords("Done: 3 steps run") == nil)
    }
}
