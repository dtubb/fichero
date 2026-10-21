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
}
