@testable import Fichero
import Foundation
import Testing

/// A slow click or expand is timed in steps, so the log names the slow part, and only a
/// selection that reaches the content hook opens a selection → content interval.
@Suite("Interaction timing splits a click into steps")
struct InteractionProfileLapsTests {

    @Test("each lap is measured from the one before it")
    func lapsAreMeasuredFromThePreviousLap() {
        let started: UInt64 = 1_000_000_000
        let laps = [
            InteractionProfile.Lap(name: "fetch", endedAt: started + 812_000_000),
            InteractionProfile.Lap(name: "splice", endedAt: started + 812_400_000),
            InteractionProfile.Lap(name: "render", endedAt: started + 842_400_000)
        ]
        #expect(
            InteractionProfile.lapBreakdown(started: started, laps: laps)
                == "fetch 812.0ms · splice 0.4ms · render 30.0ms"
        )
    }

    @Test("an interval with no laps has no breakdown")
    func noLapsNoBreakdown() {
        #expect(InteractionProfile.lapBreakdown(started: 5, laps: []).isEmpty)
    }

    @Test("only a document selection opens selection → content")
    func onlyADocumentReachesTheContentHook() {
        let libraryId = UUID()
        #expect(InteractionProfile.selectionReachesContentHook(.document("abc")))
        #expect(!InteractionProfile.selectionReachesContentHook(.trash(libraryId: libraryId)))
        #expect(!InteractionProfile.selectionReachesContentHook(.chat("c1")))
        #expect(!InteractionProfile.selectionReachesContentHook(.workflow("w1")))
        #expect(!InteractionProfile.selectionReachesContentHook(.browser(.activity)))
    }
}
