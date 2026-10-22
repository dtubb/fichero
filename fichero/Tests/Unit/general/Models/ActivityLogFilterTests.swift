//
//  ActivityLogFilterTests.swift
//  FicheroTests
//
//  activity.log.problems-first (#5960): the log's Problems · All · Everything row and its default.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

struct ActivityLogFilterTests {
    private func line(_ level: String) throws -> ActivityJobLogLine {
        let json = #"{"level": "\#(level)", "message": "m", "job_id": "j"}"#
        return ActivityJobLogLine(index: 0, try JSONDecoder().decode(Components.Schemas.JobLogLine.self, from: Data(json.utf8)))
    }

    @Test("Problems is the default while the log has a warning or an error, else All")
    func automatic() throws {
        #expect(ActivityLogFilter.automatic(hasProblems: true) == .problems)
        #expect(ActivityLogFilter.automatic(hasProblems: false) == .all)
        #expect(ActivityLogFilter.hasProblems([try line("info"), try line("warning")]))
        #expect(ActivityLogFilter.hasProblems([try line("error")]))
        #expect(!ActivityLogFilter.hasProblems([try line("info"), try line("debug")]))
        #expect(!ActivityLogFilter.hasProblems([]))
    }

    @Test("each choice asks the engine for the right read")
    func reads() {
        #expect(ActivityLogFilter.problems.problemsOnly && !ActivityLogFilter.problems.developer)
        #expect(!ActivityLogFilter.all.problemsOnly && !ActivityLogFilter.all.developer)
        #expect(!ActivityLogFilter.everything.problemsOnly && ActivityLogFilter.everything.developer)
        #expect(ActivityLogFilter.allCases.map(\.rawValue) == ["Problems", "All", "Everything"])
    }

    @Test("a choice wins; Everything, once chosen, is remembered for other rows; else the default")
    func effective() {
        #expect(ActivityLogFilter.effective(chosen: .all, developer: true, hasProblems: true) == .all)
        #expect(ActivityLogFilter.effective(chosen: nil, developer: true, hasProblems: true) == .everything)
        #expect(ActivityLogFilter.effective(chosen: nil, developer: false, hasProblems: true) == .problems)
        #expect(ActivityLogFilter.effective(chosen: nil, developer: false, hasProblems: false) == .all)
    }

    @Test("the live log follows its newest line only while live, open and at the end")
    func follows() {
        #expect(ActivityLogFollow.shouldFollow(isLive: true, isOpen: true, atEnd: true))
        #expect(!ActivityLogFollow.shouldFollow(isLive: true, isOpen: true, atEnd: false), "the person scrolled up")
        #expect(!ActivityLogFollow.shouldFollow(isLive: true, isOpen: false, atEnd: true), "the Log is closed")
        #expect(!ActivityLogFollow.shouldFollow(isLive: false, isOpen: true, atEnd: true), "a finished run's log stays put")
    }

    @Test("the closed Log says how many problems it has, and nothing when none")
    func problemCount() {
        #expect(ActivityLogFilter.problemCountWords(0) == nil)
        #expect(ActivityLogFilter.problemCountWords(1) == "1 problem")
        #expect(ActivityLogFilter.problemCountWords(3) == "3 problems")
    }
}
