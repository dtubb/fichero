@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `activity.window.run-controls` (#6588, decision 30): one Play/Pause button and Stop for all work in every open project,
/// what the button shows read from each project's engine summary.
struct ActivityRunControlsTests {
    private func summary(_ json: String) throws -> Components.Schemas.ActivitySummary {
        try JSONDecoder().decode(Components.Schemas.ActivitySummary.self, from: Data(json.utf8))
    }

    @Test("Play while any project holds work Pause All paused; Pause while anything runs; nothing when neither")
    func whatTheButtonShows() throws {
        let held = try summary(#"{"controls": "play", "stoppable": 2}"#)
        let going = try summary(#"{"controls": "pause", "stoppable": 3}"#)
        let idle = try summary(#"{"controls": "none", "stoppable": 0}"#)
        #expect(ActivityRunControlsBar.shows([going, held]) == .play)
        #expect(ActivityRunControlsBar.shows([idle, going]) == .pause)
        #expect(ActivityRunControlsBar.shows([idle, nil]) == .none)
        #expect(ActivityRunControlsBar.stoppable([going, held, nil]) == 5)
    }

    @Test("Stop All asks once, with the count")
    func stopAsksOnce() {
        #expect(ActivityRunControlsBar.stopQuestion(1) == "Stop 1 piece of work?")
        #expect(ActivityRunControlsBar.stopQuestion(41) == "Stop 41 pieces of work?")
    }
}
