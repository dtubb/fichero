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

    @Test func aPairedMacIsGivenUpOnQuickly() {
        #expect(EngineRestartPolicy.failuresBeforeRestart(workRunning: true, isLocal: false) == 3)
    }

    @Test func theGuardActsOnlyAtTheThreshold() {
        #expect(!EngineRestartPolicy.shouldRestart(failures: 35, workRunning: false))
        #expect(EngineRestartPolicy.shouldRestart(failures: 36, workRunning: false))
        #expect(!EngineRestartPolicy.shouldRestart(failures: 119, workRunning: true))
        #expect(EngineRestartPolicy.shouldRestart(failures: 120, workRunning: true))
        #expect(!EngineRestartPolicy.shouldRestart(failures: 2, workRunning: false, isLocal: false))
        #expect(EngineRestartPolicy.shouldRestart(failures: 3, workRunning: false, isLocal: false))
    }

    @Test func restartsBackOffFromTenSecondsDoublingToFiveMinutes() {
        #expect((1...6).map(EngineRestartPolicy.backoffSeconds(afterAttempt:)) == [10, 20, 40, 80, 160, 300])
        #expect(EngineRestartPolicy.backoffSeconds(afterAttempt: 40) == 300)
    }

    @Test func theSupervisorTriesFiveTimesBeforeTheRetryQuitModal() {
        #expect(EngineLifecycleController.supervisedAutoRestartAttempts == 5)
    }
}
