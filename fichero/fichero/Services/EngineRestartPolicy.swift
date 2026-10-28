import Darwin
import Foundation

/// When the app may restart a LIVE engine (`engine.restart-waits-for-the-work`, #6176; owner 2026-10-26: "far too aggressive").
/// A missed health ping only means the engine is busy: Kraken, an import or an embed can hold its event loop for many
/// seconds. The app restarts it only after it has not answered for `hungSeconds`, and for `hungWithWorkSeconds` while an
/// import or a job is running; before that it waits and says it is busy. Pure, so the patience is tested without an engine.
enum EngineRestartPolicy {
    /// The heartbeat pings this often (`AppState.startBackendHeartbeat`).
    static let pingSeconds = 5
    /// No answer for this long, with nothing running: the engine is hung.
    static let hungSeconds = 180
    /// No answer for this long while an import or a job is running.
    static let hungWithWorkSeconds = 600

    /// Jobs running in the engine, from the Activity poll (`ActivityStore`): the heartbeat's patience counts them (#6176).
    @MainActor static var runningJobs = 0

    /// A paired Mac the app cannot restart anyway: after this many missed pings it only looks for another endpoint or
    /// says it is unreachable, so the wait stays short (about 15 s).
    static let remoteFailures = 3

    /// How many missed pings in a row before the app acts on the engine: restarts a local one, or gives up on a remote one.
    static func failuresBeforeRestart(workRunning: Bool, isLocal: Bool = true) -> Int {
        guard isLocal else { return remoteFailures }
        return (workRunning ? hungWithWorkSeconds : hungSeconds) / pingSeconds
    }

    /// The wait after restart `attempt` fails, before the next: doubling from 10 s, capped at 5 minutes.
    static func backoffSeconds(afterAttempt attempt: Int) -> Int {
        min(10 << min(max(attempt - 1, 0), 5), 300)
    }

    /// Whether `failures` missed pings in a row call for action now.
    static func shouldRestart(failures: Int, workRunning: Bool, isLocal: Bool = true) -> Bool {
        failures >= failuresBeforeRestart(workRunning: workRunning, isLocal: isLocal)
    }

    /// What the heartbeat does after a missed ping.
    enum Decision: Equatable {
        /// Busy: say so, keep waiting.
        case wait
        /// The process is gone: restart now, there is nothing to wait for.
        case restartDead
        /// No answer for the whole window and no CPU or disk in it.
        case restartHung
        /// No answer for the whole window, but the process computed or wrote in it: busy, start a new window.
        case stillWorking
    }

    /// CPU or disk over a silent window that means the engine is working, not hung. An idle engine's threads use
    /// well under a second of CPU in 3 minutes. ponytail: fixed floors; learn them from runs if a busy engine trips them.
    static let workingCPUSeconds = 2.0
    static let workingDiskBytes: UInt64 = 1_000_000

    /// `windowStart` is the engine's usage at the first missed ping (or the last `.stillWorking`), `now` its usage
    /// now; nil when there is no local process to read (a paired Mac, an engine the app did not spawn).
    static func decide(
        failures: Int, workRunning: Bool, isLocal: Bool = true,
        windowStart: EngineWorkSample?, now: EngineWorkSample?, processGone: Bool
    ) -> Decision {
        if isLocal, processGone { return .restartDead }
        guard shouldRestart(failures: failures, workRunning: workRunning, isLocal: isLocal) else { return .wait }
        if isLocal, let windowStart, let now,
           now.cpuSeconds - windowStart.cpuSeconds >= workingCPUSeconds
            || now.diskBytes &- windowStart.diskBytes >= workingDiskBytes {
            return .stillWorking
        }
        return .restartHung
    }

    /// The busy line Activity shows while pings are missed (`engine.restart-waits-for-the-work`); nil when answering.
    static func busySentence(failures: Int) -> String? {
        guard failures > 0 else { return nil }
        return "The engine is busy: no answer for \(failures * pingSeconds) s. It is not restarted while it works."
    }
}

/// An engine process's lifetime CPU and disk use, read with `proc_pid_rusage`.
struct EngineWorkSample: Equatable {
    let cpuSeconds: Double
    let diskBytes: UInt64

    /// Gone only when no such process exists (ESRCH). EPERM, as the sandbox can give for usage reads, is alive.
    static func isGone(pid: pid_t) -> Bool {
        kill(pid, 0) != 0 && errno == ESRCH
    }

    /// The process's usage now; nil when it can't be read (gone, or not ours to read: see `isGone`).
    static func read(pid: pid_t) -> EngineWorkSample? {
        var info = rusage_info_v4()
        let status = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: rusage_info_t?.self, capacity: 1) { proc_pid_rusage(pid, RUSAGE_INFO_V4, $0) }
        }
        guard status == 0 else { return nil }
        // ri_*_time are mach ticks, not nanoseconds, on Apple silicon.
        var timebase = mach_timebase_info_data_t()
        mach_timebase_info(&timebase)
        let ticks = Double(info.ri_user_time + info.ri_system_time)
        return EngineWorkSample(
            cpuSeconds: ticks * Double(timebase.numer) / Double(timebase.denom) / 1e9,
            diskBytes: info.ri_diskio_bytesread + info.ri_diskio_byteswritten)
    }
}
