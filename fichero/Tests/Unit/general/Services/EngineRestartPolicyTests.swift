@testable import Fichero
import Foundation
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

    // engine.restart-waits-for-the-work: HUNG is no answer AND no CPU, no disk; DEAD is the process gone.
    private let quiet = EngineWorkSample(cpuSeconds: 10, diskBytes: 5_000_000)

    @Test func thirtyMissedPingsWithTheEngineBusyNeverRestart() {
        #expect(EngineRestartPolicy.decide(failures: 30, workRunning: false, windowStart: quiet, now: quiet,
                                           processGone: false) == .wait)
    }

    @Test func aGoneProcessIsRestartedAtOnce() {
        #expect(EngineRestartPolicy.decide(failures: 1, workRunning: true, windowStart: quiet, now: nil,
                                           processGone: true) == .restartDead)
    }

    @Test func threeSilentMinutesWithNoCPUOrDiskIsHung() {
        let barely = EngineWorkSample(cpuSeconds: 10.5, diskBytes: 5_100_000)
        #expect(EngineRestartPolicy.decide(failures: 36, workRunning: false, windowStart: quiet, now: barely,
                                           processGone: false) == .restartHung)
    }

    @Test func threeSilentMinutesWhileTheEngineComputesIsBusyNotHung() {
        let computing = EngineWorkSample(cpuSeconds: 150, diskBytes: 5_000_000)
        let writing = EngineWorkSample(cpuSeconds: 10, diskBytes: 80_000_000)
        #expect(EngineRestartPolicy.decide(failures: 36, workRunning: false, windowStart: quiet, now: computing,
                                           processGone: false) == .stillWorking)
        #expect(EngineRestartPolicy.decide(failures: 36, workRunning: false, windowStart: quiet, now: writing,
                                           processGone: false) == .stillWorking)
    }

    @Test func withNoProcessToReadTheClockAloneDecides() {
        #expect(EngineRestartPolicy.decide(failures: 36, workRunning: false, windowStart: nil, now: nil,
                                           processGone: false) == .restartHung)
        #expect(EngineRestartPolicy.decide(failures: 3, workRunning: false, isLocal: false, windowStart: nil,
                                           now: nil, processGone: false) == .restartHung)
    }

    @Test func aProcessWeMayNotReadIsAliveNotGone_onlyNoSuchProcessIsGone() throws {
        // launchd's usage is not ours to read (EPERM), as the sandbox gives for the engine: never "dead".
        #expect(!EngineWorkSample.isGone(pid: 1))
        #expect(!EngineWorkSample.isGone(pid: getpid()))
        let done = Process()
        done.executableURL = URL(fileURLWithPath: "/usr/bin/true")
        try done.run()
        done.waitUntilExit()
        #expect(EngineWorkSample.isGone(pid: done.processIdentifier))
    }

    @Test func theBusyLineSaysHowLongTheEngineHasNotAnswered() {
        #expect(EngineRestartPolicy.busySentence(failures: 0) == nil)
        #expect(EngineRestartPolicy.busySentence(failures: 7)
            == "The engine is busy: no answer for 35 s. It is not restarted while it works.")
    }
}
