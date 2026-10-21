import FicheroAPIClient
import Foundation
import Testing
@testable import Fichero

/// `activity.window.stage-bar` (#5960, #5871): a finished stage's segment is full, so the row never looks as if it went back.
struct ActivityStageBarTests {
    private func card(_ state: ActivityStageCardState, done: Int = 0, total: Int = 0, failed: Int = 0) -> ActivityDetails.StageCard {
        ActivityDetails.StageCard(id: "read", title: "Read", state: state, done: done, total: total,
                                  made: [], why: nil, offersSetUp: false, failed: nil, pagesFailed: failed)
    }

    @Test func aFinishedStageIsFullEvenWhenItsCountMovedBack() {
        #expect(ActivityStageBar.segments(of: [card(.done, done: 3, total: 10)]).first?.fill == 1)
        #expect(ActivityStageBar.segments(of: [card(.done)]).first?.fill == 1)
    }

    @Test func aPartialStageIsFullAndHatched() {
        let segment = ActivityStageBar.segments(of: [card(.partial, done: 8, total: 10)]).first
        #expect(segment?.fill == 1 && segment?.hatched == true)
    }

    @Test func aRunningStageFillsByPagesDone() {
        #expect(ActivityStageBar.segments(of: [card(.running, done: 4, total: 10)]).first?.fill == 0.4)
        #expect(ActivityStageBar.segments(of: [card(.running, done: 12, total: 10)]).first?.fill == 1)
    }

    @Test func aWaitingStageIsEmptyAndASkippedStageHasNoSegment() {
        #expect(ActivityStageBar.segments(of: [card(.waiting)]).first?.fill == 0)
        #expect(ActivityStageBar.segments(of: [card(.skipped)]).isEmpty)
    }

    @Test func aFailedStageCarriesTheTick() {
        #expect(ActivityStageBar.segments(of: [card(.failed, done: 2, total: 10, failed: 3)]).first?.failedPages == 3)
    }

    @Test func aFinishedStageWithFailedPagesIsFullAndHatchedWithATickPerFailedPage() {
        let segment = ActivityStageBar.segments(of: [card(.done, done: 7, total: 10, failed: 3)]).first
        #expect(segment?.fill == 1 && segment?.hatched == true && segment?.failedPages == 3)
        #expect(ActivityStageBar.segments(of: [card(.done, done: 10, total: 10)]).first?.hatched == false)
    }

    @Test func aSecondProjectsRowGetsItsBarFromItsOwnStore() throws {
        let tree = try JSONDecoder().decode(Components.Schemas.JobTree.self,
                                            from: Data(ActivityStageCardsTests.treeJSON.utf8))
        let first = UUID(), second = UUID()
        let node = try JSONDecoder().decode(Components.Schemas.JobTree.self, from: Data("""
        {"id":"r1","kind":"run-a-recipe","name":"Run","subject":"r1","state":"running","done":0,"total":0}
        """.utf8))
        let run = ActivityRun(node: ActivityJobNode(node), libraryId: second, libraryName: "Second")
        let row = ActivityMonitorRow.run(run, tree: nil)
        let trees = [first: [String: ActivityJobNode](), second: ["r1": ActivityJobNode(tree)]]
        #expect(!ActivityStageBar.segments(for: row, trees: trees).isEmpty)
        #expect(ActivityStageBar.segments(for: row, trees: [first: trees[second] ?? [:]]).isEmpty)  // not the other's
    }

    @Test func theSegmentSaysItsStateAndItsFailuresForVoiceOver() {
        let partial = ActivityStageBar.segments(of: [card(.partial, done: 7, total: 10, failed: 3)]).first
        #expect(partial?.label == "Read, partial, 3 failed")
        #expect(ActivityStageBar.segments(of: [card(.running, done: 1, total: 10)]).first?.label == "Read, running")
    }

    @Test func twoStoresWithOneLibraryIdKeepTheFirstAndDoNotCrash() throws {
        let id = UUID()
        let tree = try JSONDecoder().decode(Components.Schemas.JobTree.self,
                                            from: Data(ActivityStageCardsTests.treeJSON.utf8))
        let trees = ActivityStageBar.trees([(id, ["r1": ActivityJobNode(tree)]), (id, [:])])
        #expect(trees.count == 1 && trees[id]?["r1"] != nil)
    }

    @Test func ticksSpreadAcrossTheWholeSegmentWhenNothingIsFilled() {
        let empty = ActivityStageBar.tickPositions(count: 3, fill: 0)
        #expect(empty == [0.25, 0.5, 0.75])
        #expect(Set(empty).count == 3)  // not stacked at the start
        #expect(ActivityStageBar.tickPositions(count: 1, fill: 0.4) == [0.2])  // along the filled part
        #expect(ActivityStageBar.tickPositions(count: 9, fill: 1).count == ActivityStageBar.maxTicks)
    }
}
