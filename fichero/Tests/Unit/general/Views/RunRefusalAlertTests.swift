@testable import Fichero
import Testing

/// `runner.hand-run.same-contract`: Start and the folder's run show the engine's refusal where the person pressed.
@Suite("Run refusal alert")
struct RunRefusalAlertTests {
    @Test("the engine's error from the start call comes first")
    func startError() {
        #expect(RunRefusalAlert.words(startError: "This project has no material yet.", planRefusals: ["other"])
                == "This project has no material yet.")
    }

    @Test("a plan that cannot start says its first refusal")
    func planRefusal() {
        #expect(RunRefusalAlert.words(startError: nil, planRefusals: ["A cloud step is off", "x"]) == "A cloud step is off")
    }

    @Test("with no words at all the alert still says something")
    func fallback() {
        #expect(RunRefusalAlert.words(startError: "", planRefusals: []) == RunRefusalAlert.fallback)
    }
}
