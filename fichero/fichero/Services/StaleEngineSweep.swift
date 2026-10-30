import Foundation

/// Which leftover "Fichero Server" helpers the app ends before it starts its own engine
/// (spec `engine.stale-engines-ended-at-launch`).
///
/// PURE: a process table in, the pids to end out. The caller reads the table (`ps`, in
/// `EmbeddedBackendService+Ports.swift`, the one file allowed to carry that machinery) and signals the pids; nothing
/// here touches a process, so every rule below is a unit test.
///
/// A process is STALE only if ALL of these hold; the answer to any doubt is to spare it:
///   1. its executable is `<bundle>/Contents/MacOS/Fichero Server` inside a `Fichero Server.app` that is itself, or
///      lies inside, an app bundle named `Fichero*.app` — never a uvicorn/python dev engine (its path is a venv or a
///      system Python, not a bundle: the maintainer's external dev engine, #6244, is out of scope by construction);
///   2. it belongs to this user — never another user's;
///   3. it is an ORPHAN: its parent is launchd (pid 1) or no longer in the table. A helper whose parent is alive is a
///      live app's engine — this app's own, or another copy of the app (two copies are two bundles, each live while its
///      own app process runs), or one a person started from a shell — and is left alone.
nonisolated enum StaleEngineSweep {
    struct ProcessFact: Equatable, Sendable {
        let pid: Int32
        let parentPID: Int32
        let uid: UInt32
        let executablePath: String
    }

    /// The pids to end, ascending. `ownPID` (this app) is never one of them.
    static func pidsToEnd(table: [ProcessFact], currentUID: UInt32, ownPID: Int32) -> [Int32] {
        let alive = Set(table.map(\.pid))
        return table
            .filter { $0.pid != ownPID && $0.uid == currentUID }
            .filter { isFicheroServerHelper(executablePath: $0.executablePath) }
            .filter { $0.parentPID <= 1 || !alive.contains($0.parentPID) }
            .map(\.pid)
            .sorted()
    }

    /// `…/Fichero Server.app/Contents/MacOS/Fichero Server`. A bundle named `Fichero Server.app` is itself a
    /// `Fichero*.app`, so this one test also covers "inside an app bundle named Fichero*.app". A venv's
    /// `python`, a Homebrew `Python.app`, `uvicorn` and any other app's helper fail it.
    static func isFicheroServerHelper(executablePath: String) -> Bool {
        let parts = executablePath.split(separator: "/", omittingEmptySubsequences: true).map(String.init)
        guard parts.count >= 4 else { return false }
        let tail = Array(parts.suffix(4))
        return tail == ["Fichero Server.app", "Contents", "MacOS", "Fichero Server"]
    }

    /// Reads `ps -axo pid=,ppid=,uid=,comm=` output. `comm` is last because a path holds spaces; a line that does
    /// not start with three integers is skipped.
    static func parseTable(_ output: String) -> [ProcessFact] {
        output.split(separator: "\n").compactMap { line in
            let fields = line.split(separator: " ", maxSplits: 3, omittingEmptySubsequences: true)
            guard fields.count == 4,
                  let pid = Int32(fields[0]), let parent = Int32(fields[1]), let uid = UInt32(fields[2])
            else { return nil }
            return ProcessFact(pid: pid, parentPID: parent, uid: uid, executablePath: String(fields[3]))
        }
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

    /// "Ended 1 leftover Fichero Server from an earlier run." — the one line for the connection status.
    static func notice(ended: [Int32]) -> String? {
        guard !ended.isEmpty else { return nil }
        let noun = ended.count == 1 ? "1 leftover Fichero Server" : "\(ended.count) leftover Fichero Servers"
        return "Ended \(noun) from an earlier run."
    }
}
