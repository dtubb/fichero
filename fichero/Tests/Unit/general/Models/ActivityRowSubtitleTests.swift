@testable import Fichero
import Foundation
import Testing

/// `activity.window.row-subtitle` (#5960): counts, the time left from the engine's pace, the model and where it runs; the cost only when it
/// is more than nothing.
struct ActivityRowSubtitleTests {
    @Test("the time left in minutes, hours to the half hour, and a minute under a minute and a half")
    func timeLeft() {
        #expect(ActivityPopoverSummary.timeLeft(seconds: 40) == "less than a minute left")
        #expect(ActivityPopoverSummary.timeLeft(seconds: 12 * 60) == "about 12 min left")
        #expect(ActivityPopoverSummary.timeLeft(seconds: 2 * 3600) == "about 2 h left")
        #expect(ActivityPopoverSummary.timeLeft(seconds: 5400 + 600) == "about 1.5 h left")
    }

    @Test("no pace, no words")
    func noPace() {
        #expect(ActivityPopoverSummary.timeLeft(seconds: nil) == nil)
        #expect(ActivityPopoverSummary.timeLeft(seconds: 0) == nil)
    }

    @Test("the cost shows only when it is more than nothing")
    func cost() {
        #expect(ActivityPopoverSummary.costText(nil) == nil)
        #expect(ActivityPopoverSummary.costText(0) == nil)
        #expect(ActivityPopoverSummary.costText(0.004) == "<$0.01")
        #expect(ActivityPopoverSummary.costText(0.4) == "$0.40")
    }

    @Test("counts, time left, model and where, in that order, each only if known")
    func line() {
        let full = ActivityPopoverSummary.rowSubtitle(counts: "7 of 20 pages", secondsLeft: 720, model: "Kraken", place: "on this Mac")
        #expect(full == "7 of 20 pages · about 12 min left · Kraken · on this Mac")
        #expect(ActivityPopoverSummary.rowSubtitle(counts: "7 of 20 pages", secondsLeft: nil, model: nil, place: nil) == "7 of 20 pages")
    }
}
