//
//  ActivityOpenedRunTests.swift
//  FicheroTests
//
//  activity.window.open-a-run (#5960): an opened run is one scroll view whose Details and Log are disclosures, closed by
//  default and remembered; the log is not a list inside another scroll. A source pin: these are layout rules.
//

@testable import Fichero
import Foundation
import Testing

struct ActivityOpenedRunTests {
    private func source(_ path: String) throws -> String {
        try String(contentsOf: try AppSource.root().appendingPathComponent(path), encoding: .utf8)
    }

    @Test("Details and Log are disclosures with remembered keys, and the stage bar leads the page")
    func disclosures() throws {
        let view = try source("Views/Activity/Detail/ActivityDetailsView.swift")
        #expect(view.contains(#"ActivityDetailsDisclosure("Details", key: "activity.opened.details")"#))
        #expect(view.contains(#"ActivityDetailsDisclosure("Log", detail:"#) && view.contains(#"key: "activity.opened.log""#))
        #expect(view.contains("ActivityStageBar(segments: bar)"))
        let disclosure = try source("Views/Activity/Detail/ActivityDetailsDisclosure.swift")
        #expect(disclosure.contains("AppStorage(wrappedValue: false, key)"), "closed by default, kept under its key")
    }

    @Test("the log is not a list inside another scroll")
    func logIsNotAScrollOfItsOwn() throws {
        let view = try source("Views/Activity/Detail/ActivityDetailsView.swift")
        let log = try #require(view.range(of: "struct ActivityDetailsLog: View"))
        let end = try #require(view.range(of: "struct ActivityDetailsLogPane"))
        let body = String(view[log.lowerBound..<end.lowerBound])
        #expect(!body.contains("List(lines)"))
        #expect(!body.contains("ScrollViewReader"))
        #expect(body.contains("LazyVStack"))
    }

    @Test("the subtitle says when the run started: the time for today, the day for another day, nothing when not known")
    func startedAt() {
        let now = Date(timeIntervalSince1970: 1_792_000_000)
        let time = now.formatted(date: .omitted, time: .shortened)
        #expect(ActivityDetails.startedAtWords(now, now: now) == "at \(time)")
        let earlier = now.addingTimeInterval(-3 * 86_400)
        let words = ActivityDetails.startedAtWords(earlier, now: now) ?? ""
        #expect(words.hasSuffix(earlier.formatted(date: .omitted, time: .shortened)) && !words.hasPrefix("at "))
        #expect(ActivityDetails.startedAtWords(nil, now: now) == nil)
    }

    @Test("the failed pages carry the run's ONE Read them again, and the actions do not say it a second time")
    func oneReadThemAgain() throws {
        let sections = try source("Views/Activity/Detail/ActivityDetailsSections.swift")
        #expect(sections.components(separatedBy: #"Button("Read them again")"#).count == 2, "exactly one such button")
        let view = try source("Views/Activity/Detail/ActivityDetailsView.swift")
        #expect(view.contains("ActivityDetailsFailedPages(details: details, readAgain: runTarget(details))"))
        #expect(view.contains("hidesReadAgain: !details.failedPages.isEmpty && runTarget(details).readAgainLabel != nil"))
    }

    @Test("the run's line says how many pages it reads at once and why, as the engine sends them (#6217)")
    func pagesAtOnce() {
        #expect(RecipeRunPagesAtOnce(count: 2, reason: nil).words == "reading 2 pages at once")
        #expect(RecipeRunPagesAtOnce(count: 1, reason: "the Mac is paging").words == "one page at a time: the Mac is paging")
        #expect(RecipeRunPagesAtOnce(count: 1, reason: nil).words == "one page at a time")
        let strip = ProjectRunStrip(jobId: "r", node: nil, job: nil, folders: nil,
                                    pagesAtOnce: RecipeRunPagesAtOnce(count: 1, reason: "resuming after a restart"))
        #expect(strip.detail.hasSuffix("one page at a time: resuming after a restart"))
    }

    @Test("an opened run's grey line says how many pages it reads at once while it runs, as the engine sends it (#6217)")
    func pagesAtOnceOnTheOpenedRun() {
        func details(_ state: ActivityJob.State) -> ActivityDetails {
            let row = ActivityMonitorRow.job(
                ActivityJob(id: "run-1", taskType: "run-a-recipe", name: "Recipe run", current: 1, total: 4, state: state),
                libraryId: nil, projectName: nil)
            return ActivityDetails(row: row, node: nil, runRow: nil, projectName: nil, startedBy: nil, machine: nil,
                                   pagesAtOnce: RecipeRunPagesAtOnce(count: 1, reason: "the Mac is paging"))
        }
        #expect(details(.running).subheading.contains("one page at a time: the Mac is paging"))
        #expect(!details(.completed).subheading.contains("one page at a time: the Mac is paging"), "an ended run reads no pages")
    }

    @Test("a stage's counts say the first pages in order while a page finished ahead of a gap (#6186)")
    func doneInOrder() {
        let ahead = ActivityRunAccount(state: "running", pagesTotal: 20, pagesDone: 12, pagesLeft: 8, pagesDoneInOrder: 9)
        #expect(ActivityDetails.countsWords(ahead) == "12 done · 0 failed · 8 left · first 9 in order")
        let inOrder = ActivityRunAccount(state: "running", pagesTotal: 20, pagesDone: 12, pagesLeft: 8, pagesDoneInOrder: 12)
        #expect(ActivityDetails.countsWords(inOrder) == "12 done · 0 failed · 8 left")
        let older = ActivityRunAccount(state: "running", pagesTotal: 20, pagesDone: 12, pagesLeft: 8)
        #expect(ActivityDetails.countsWords(older) == "12 done · 0 failed · 8 left", "an engine without the field says nothing of order")
    }
}
