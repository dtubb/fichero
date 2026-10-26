@testable import Fichero
import Testing

struct EngineRestartPolicyTests {
    @Test func aBusyEngineIsGivenThreeMinutesOfMissedPings() {
        #expect(EngineRestartPolicy.failuresBeforeRestart(workRunning: false) == 36)
    }

    @Test func anEngineRunningWorkIsGivenTenMinutes() {
        #expect(EngineRestartPolicy.failuresBeforeRestart(workRunning: true) == 120)
    }

    @Test func theOldTwoMissedPingsNeverRestartAnEngineAgain() {
        #expect(EngineRestartPolicy.failuresBeforeRestart(workRunning: false) > 2)
        #expect(EngineRestartPolicy.failuresBeforeRestart(workRunning: true) > 8)
    }
}
