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

    /// `started` and `ended` are nil unless a test gives them: a helper that dated every row today would hide the rows
    /// the engine sends with no start (a job of its own) or one that began yesterday (## 745).
    private func row(_ id: String, _ phase: Phase, kind: ActivityMonitorRow.Kind = .run, started: Date? = nil,
                     ended: Date? = nil, queue: Int? = nil, jobId: String? = "job",
                     reason: String? = nil, project: String? = nil) -> ActivityMonitorRow {
        var row = ActivityMonitorRow(
            id: id, kind: kind, libraryId: nil, runRowID: nil, runThreadId: nil, jobId: jobId, name: id, projectName: project,
            phase: phase, reason: reason, workingOn: nil, done: 0, total: 0, started: started, seconds: nil, costUsd: nil,
            tokens: 0, errors: 0, model: nil, isLive: phase.isLive, children: nil, account: nil
        )
        row.queuePosition = queue
        row.ended = ended
        return row
    }

    @Test("running and paused rows are NOW, waiting rows UP NEXT in lane order, ended rows DONE TODAY newest first")
    func threeGroups() {
        let groups = ActivityWindowGroups(rows: [
            row("late", .waiting, queue: 2), row("run", .running), row("early", .waiting, queue: 1), row("held", .paused),
            row("old", .done, ended: today.addingTimeInterval(-60)), row("new", .partial, ended: today.addingTimeInterval(-10)),
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
        #expect(ActivityWindowGroups(rows: [row("old", .done, started: yesterday, ended: yesterday)], now: today).isEmpty)
        #expect(ActivityWindowGroups(rows: [], now: today).isEmpty)
    }

    @Test("DONE TODAY goes by the END time: an overnight run that ended today is in, a row with no known end is not")
    func endTimeNotStartTime() {
        let yesterday = today.addingTimeInterval(-86_400)
        let groups = ActivityWindowGroups(rows: [
            row("job", .done, kind: .job), row("overnight", .done, started: yesterday, ended: today.addingTimeInterval(-300)),
            row("ended-yesterday", .done, started: yesterday, ended: yesterday),
            row("started-today-ended-never", .done, started: today.addingTimeInterval(-10)),
        ], now: today)
        #expect(groups.doneToday.map(\.id) == ["overnight"])
    }

    @Test("a run and the job row of the same work are one row: the run")
    func runAndItsOwnJobAreOne() {
        let groups = ActivityWindowGroups(rows: [
            row("run", .running, jobId: "j1"), row("job", .running, kind: .job, jobId: "j1"),
            row("other", .running, kind: .job, jobId: "j2"),
        ], now: today)
        #expect(groups.now.map(\.id) == ["run", "other"])
    }

    @Test("a not-run row settled today stays in DONE TODAY with its reason shown")
    func notRunKeepsItsReason() {
        let skipped = row("skipped", .notRun, ended: today.addingTimeInterval(-5), reason: "no model for it")
        #expect(ActivityWindowGroups(rows: [skipped], now: today).doneToday.map(\.id) == ["skipped"])
        #expect(skipped.stateText.contains("no model for it"))
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

    @Test("with one project's work in the window a row names no project; with several, the project leads the name")
    func projectPrefix() {
        let named = row("Read the box", .running, project: "Mosquera")
        #expect(named.displayName(showsProject: false) == "Read the box")
        #expect(named.displayName(showsProject: true) == "Mosquera · Read the box")
        #expect(row("Read the box", .running).displayName(showsProject: true) == "Read the box")  // no project name to lead
        #expect(row("Read the box", .running, project: "").displayName(showsProject: true) == "Read the box")
    }
}
