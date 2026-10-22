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
}
