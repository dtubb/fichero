import Foundation

/// Which leftover "Fichero Server" helpers the app ends before it starts its own engine
/// (spec `engine.stale-engines-ended-at-launch`).
///
/// PURE: a process table in, the pids to end out. The caller reads the table (`ps`, in
/// `EmbeddedBackendService+Ports.swift`, the one file allowed to carry that machinery) and signals the pids; nothing
/// here touches a process, so every rule below is a unit test.
///
/// A process is STALE only if ALL of these hold; the answer to any doubt is to spare it:
///   1. its REAL executable (`proc_pidpath`, never `ps`'s argv[0], which a process can set to anything) is
///      `<Fichero*.app>/…/Fichero Server.app/Contents/MacOS/Fichero Server`: the helper INSIDE an outer app bundle
///      named `Fichero*.app`. A helper in /tmp or a build folder, a uvicorn/python dev engine (a venv or system
///      Python, not a bundle: the maintainer's external dev engine, #6244) and any other app's helper are out;
///   2. it belongs to this user — never another user's;
///   3. it is an ORPHAN: its parent is launchd (pid 1) or no longer in the table. A helper whose parent is alive is a
///      live app's engine — this app's own, or another copy of the app (two copies are two bundles, each live while its
///      own app process runs), or one a person started from a shell — and is left alone;
///   4. an app launched it, and that app run is over: its `FICHERO_PARENT_PID` (set by `buildChildEnvironment`) names
///      this app or a process that no longer exists. A launchd-parented helper with NO recorded parent was started
///      independently of any app run (`open`, a kept-warm or shared engine, #5272): it is SPARED, exactly as the old
///      #2079 rule did, and so is one whose environment cannot be read. A recorded parent that is alive and is not this
///      app is a different live owner: spared;
///   5. never pid 1 or below, never this app's own pid.
/// Just before each signal the caller re-reads the process and ends it only if `isStillTheSame` says it is the one
/// that was chosen (a pid is reused once a process dies).
nonisolated enum StaleEngineSweep {
    struct ProcessFact: Equatable, Sendable {
        let pid: Int32
        let parentPID: Int32
        let uid: UInt32
        let executablePath: String
        /// `FICHERO_PARENT_PID` from the process's environment: nil when absent or unreadable (then it is spared).
        let recordedParentPID: Int32?

        init(pid: Int32, parentPID: Int32, uid: UInt32, executablePath: String, recordedParentPID: Int32? = nil) {
            self.pid = pid
            self.parentPID = parentPID
            self.uid = uid
            self.executablePath = executablePath
            self.recordedParentPID = recordedParentPID
        }
    }

    /// The pids to end, ascending. `ownPID` (this app) is never one of them.
    static func pidsToEnd(table: [ProcessFact], currentUID: UInt32, ownPID: Int32) -> [Int32] {
        let alive = Set(table.map(\.pid))
        return table
            .filter { $0.pid > 1 && $0.pid != ownPID && $0.uid == currentUID }
            .filter { isFicheroServerHelper(executablePath: $0.executablePath) }
            .filter { $0.parentPID <= 1 || !alive.contains($0.parentPID) }
            .filter { fact in
                guard let recorded = fact.recordedParentPID else { return false }
                return recorded == ownPID || !alive.contains(recorded)
            }
            .map(\.pid)
            .sorted()
    }

    /// The process now at `chosen.pid` is the one that was chosen: same executable, owner and parent. `nil` (gone) or
    /// anything else (the pid was reused) is not, and must not be signalled.
    static func isStillTheSame(_ chosen: ProcessFact, now: ProcessFact?) -> Bool {
        guard let now else { return false }
        return now.pid == chosen.pid && now.uid == chosen.uid && now.parentPID == chosen.parentPID
            && now.executablePath == chosen.executablePath
    }

    /// `…/Fichero*.app/…/Fichero Server.app/Contents/MacOS/Fichero Server`: the helper, inside an outer bundle whose
    /// name starts `Fichero` and ends `.app` (`Fichero.app`, `Fichero Dev.app`, `Fichero 2.app`).
    static func isFicheroServerHelper(executablePath: String) -> Bool {
        let parts = executablePath.split(separator: "/", omittingEmptySubsequences: true).map(String.init)
        guard parts.count >= 5, Array(parts.suffix(4)) == ["Fichero Server.app", "Contents", "MacOS", "Fichero Server"]
        else { return false }
        return parts.dropLast(4).contains { $0.hasPrefix("Fichero") && $0.hasSuffix(".app") }
    }

    /// `FICHERO_PARENT_PID` from a `KERN_PROCARGS2` buffer: `argc` (Int32), the executable path, NUL padding, `argc`
    /// argument strings, then the environment strings. nil when the buffer is short or the variable is absent.
    static func recordedParentPID(procArgs: [UInt8]) -> Int32? {
        guard procArgs.count > 4 else { return nil }
        let argc = Int(procArgs[0]) | Int(procArgs[1]) << 8 | Int(procArgs[2]) << 16 | Int(procArgs[3]) << 24
        var strings = procArgs.dropFirst(4).split(separator: 0, omittingEmptySubsequences: false)
        // The first string is the executable path; empty ones are the NUL padding after it.
        guard !strings.isEmpty else { return nil }
        strings.removeFirst()
        let rest = strings.filter { !$0.isEmpty }
        guard rest.count >= argc else { return nil }
        let prefix = Array("FICHERO_PARENT_PID=".utf8)
        for entry in rest.dropFirst(argc) where entry.starts(with: prefix) {
            return Int32(String(decoding: entry.dropFirst(prefix.count), as: UTF8.self))
        }
        return nil
    }

    // MARK: - What the last sweep ended (read once by the main actor for the one-line notice)

    private static let recordedLock = NSLock()
    nonisolated(unsafe) private static var recordedEnded: [Int32] = []

    static func record(ended: [Int32]) {
        recordedLock.lock()
        defer { recordedLock.unlock() }
        recordedEnded.append(contentsOf: ended)
    }

    /// Returns the pids ended since the last call, and forgets them: the notice is shown once.
    static func takeEnded() -> [Int32] {
        recordedLock.lock()
        defer { recordedLock.unlock() }
        defer { recordedEnded = [] }
        return recordedEnded
    }

    /// The notice after a launch step: a NEW line when the sweep ended something, else the one already showing. A later
    /// respawn that ends nothing must not wipe the line of the launch that did.
    static func nextNotice(current: String?, ended: [Int32]) -> String? {
        notice(ended: ended) ?? current
    }

    /// "Ended 1 leftover Fichero Server from an earlier run." — the one line for the connection status.
    static func notice(ended: [Int32]) -> String? {
        guard !ended.isEmpty else { return nil }
        let noun = ended.count == 1 ? "1 leftover Fichero Server" : "\(ended.count) leftover Fichero Servers"
        return "Ended \(noun) from an earlier run."
    }
}
