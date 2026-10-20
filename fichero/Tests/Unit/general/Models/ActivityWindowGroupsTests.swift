//
//  ActivityWindowGroupsTests.swift
//  FicheroTests
//
//  #5960: the window's three groups and a row's one button. Specs: `activity.window.three-groups`,
//  `activity.window.one-row-per-run`, `activity.window.up-next`, `activity.window.done-today`, `activity.window.one-button`.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct ActivityWindowGroupsTests {
    typealias Phase = ActivityMonitorRow.Phase

    private let today = Date(timeIntervalSince1970: 1_792_000_000)

    private func row(_ id: String, _ phase: Phase, kind: ActivityMonitorRow.Kind = .run, started: Date? = nil,
                     queue: Int? = nil, jobId: String? = "job") -> ActivityMonitorRow {
        var row = ActivityMonitorRow(
            id: id, kind: kind, libraryId: nil, runRowID: nil, runThreadId: nil, jobId: jobId, name: id, projectName: nil,
            phase: phase, reason: nil, workingOn: nil, done: 0, total: 0, started: started ?? today, seconds: nil, costUsd: nil,
            tokens: 0, errors: 0, model: nil, isLive: phase.isLive, children: nil, account: nil
        )
        row.queuePosition = queue
        return row
    }

    @Test("running and paused rows are NOW, waiting rows UP NEXT in lane order, ended rows DONE TODAY newest first")
    func threeGroups() {
        let groups = ActivityWindowGroups(rows: [
            row("late", .waiting, queue: 2), row("run", .running), row("early", .waiting, queue: 1), row("held", .paused),
            row("old", .done, started: today.addingTimeInterval(-60)), row("new", .partial, started: today.addingTimeInterval(-10)),
        ], now: today)
        #expect(groups.now.map(\.id) == ["run", "held"])
        #expect(groups.upNext.map(\.id) == ["early", "late"])
        #expect(groups.doneToday.map(\.id) == ["new", "old"])
    }

    @Test("a run is one row: steps and pages are never list rows")
    func oneRowPerRun() {
        let groups = ActivityWindowGroups(rows: [row("run", .running), row("step", .running, kind: .step), row("page", .done, kind: .page)], now: today)
        #expect(groups.now.map(\.id) == ["run"] && groups.doneToday.isEmpty)
    }

    @Test("what ended on another day is not DONE TODAY, and nothing at all is empty")
    func onlyToday() {
        let yesterday = today.addingTimeInterval(-3 * 86_400)
        #expect(ActivityWindowGroups(rows: [row("old", .done, started: yesterday)], now: today).isEmpty)
        #expect(ActivityWindowGroups(rows: [], now: today).isEmpty)
    }

    @Test("a row has one button, or none: pause, resume, retry or show; a waiting row has none")
    func oneButton() {
        #expect(row("a", .running).oneButton == .pause)
        #expect(row("a", .paused).oneButton == .resume)
        #expect(row("a", .waiting).oneButton == nil)
        #expect(row("a", .partial).oneButton == .retry)
        #expect(row("a", .failed).oneButton == .retry)
        #expect(row("a", .failed, jobId: nil).oneButton == .show)
        #expect(row("a", .done).oneButton == .show)
        #expect(row("a", .unknown).oneButton == .show)
        #expect(row("a", .running, jobId: nil).oneButton == nil)
    }
}
