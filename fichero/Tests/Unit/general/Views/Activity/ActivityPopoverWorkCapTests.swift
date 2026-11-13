//
//  ActivityPopoverWorkCapTests.swift
//  FicheroTests
//
//  activity.popover.at-most-five (owner 2026-11-13): the popover names at most five pieces of work, in order, and the
//  rest are one "N more in Activity" line. See docs/contributor_manual/specs/ui/activity-and-automatic-work.md.
//

@testable import Fichero
import Testing

struct ActivityPopoverWorkCapTests {
    typealias Cap = ActivityPopoverSummary.WorkCap

    @Test("a dozen running workflows: five are named, seven are left to Activity")
    func aDozenRunsShowFive() {
        let cap = Cap(blocks: 0, runs: 0, background: 0, running: 12)
        #expect(cap.running == 5)
        #expect(cap.hidden == 7)
        #expect(cap.moreLine == "7 more in Activity")
    }

    @Test("the five go to live blocks first, then runs, background, running")
    func theOrderIsKept() {
        let cap = Cap(blocks: 2, runs: 2, background: 3, running: 4)
        #expect([cap.blocks, cap.runs, cap.background, cap.running] == [2, 2, 1, 0])
        #expect(cap.hidden == 6)
    }

    @Test("five or fewer pieces of work are all named, with no more line")
    func fewIsAll() {
        let cap = Cap(blocks: 1, runs: 1, background: 1, running: 2)
        #expect([cap.blocks, cap.runs, cap.background, cap.running] == [1, 1, 1, 2])
        #expect(cap.moreLine == nil)
        #expect(ActivityPopoverSummary.workShown == 5)
    }
}
