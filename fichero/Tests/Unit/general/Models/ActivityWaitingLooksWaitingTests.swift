//
//  ActivityWaitingLooksWaitingTests.swift
//  FicheroTests
//
//  #5839 (owner, 2026-10-19): Activity shows the run order, and a waiting job looks waiting until it starts: no spinner,
//  no progress, no ticking timer, a grey "Waiting: <reason>". Spec: `activity.window.waiting-looks-waiting`.
//

@testable import Fichero
import Foundation
import XCTest

@MainActor
final class ActivityWaitingLooksWaitingTests: XCTestCase {
    private func row(phase: ActivityMonitorRow.Phase, reason: String? = nil, done: Int = 0, total: Int = 1,
                     account: ActivityRunAccount? = nil, started: Date? = nil) -> ActivityMonitorRow {
        ActivityMonitorRow(
            id: UUID().uuidString, kind: .run, libraryId: nil, runRowID: nil, runThreadId: nil, jobId: "j",
            name: "Try a stage", projectName: nil, phase: phase, reason: reason, workingOn: nil, done: done,
            total: total, started: started, seconds: 5, costUsd: nil, tokens: 0, errors: 0, model: nil,
            isLive: true, children: nil, account: account
        )
    }

    func testAWaitingRowShowsNoProgressOrTimeAndSaysWhy() {
        let waiting = row(phase: .waiting, reason: "the model lane: Kraken read")
        XCTAssertTrue(waiting.looksWaiting)
        XCTAssertEqual(waiting.stateText, "Waiting: the model lane: Kraken read")
        XCTAssertEqual(waiting.progressText, "")
        XCTAssertEqual(waiting.secondsText, "")
    }

    func testARunWhoseOnePageWaitsWhileAnotherRunsIsRunningNotWaiting() {
        // WHY: review 233: page 1 running and page 2 waiting leaves done 0; the row is going, so it keeps its progress.
        let account = ActivityRunAccount(state: "running", pagesTotal: 2, pagesDone: 0, pagesLeft: 2,
                                         waitingReason: "Waiting: the model lane", estimateSecondsLeft: nil)
        let going = row(phase: .running, done: 0, total: 2, account: account)
        XCTAssertFalse(going.looksWaiting)
        XCTAssertEqual(going.progressText, "0 of 2")
    }

    func testTheDefaultOrderIsRunningThenWaitingInTheEnginesQueueOrder() {
        var next = row(phase: .waiting, reason: "x"); next.queuePosition = 0
        var later = row(phase: .waiting, reason: "x"); later.queuePosition = 1
        let running = row(phase: .running, done: 1, total: 4)
        let sorted = ActivityMonitorRow.sorted([later, next, running], using: ActivityMonitorRow.defaultSort)
        XCTAssertEqual(sorted.map(\.id), [running.id, next.id, later.id])
    }
}
