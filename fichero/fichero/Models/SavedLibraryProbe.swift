import Foundation

/// Whether each saved library path exists, asked off the calling thread with a timeout per library (#7105).
///
/// `FileManager.fileExists` on an unmounted, slow or iCloud volume can block for minutes, and launch asked it on the
/// main thread for every saved library. Here every path is asked at once on a global queue; the caller waits `timeout`
/// and goes on with what answered. A path that answers after that is handed to `late`, on the queue's thread.
///
/// ponytail: a path that never answers holds one global-queue thread until its volume does; a cancellable probe
/// (a child process, or `URLResourceValues` on an `OperationQueue` with a deadline) if many saved volumes hang at once.
nonisolated enum SavedLibraryProbe {
    enum Answer: Equatable, Sendable {
        case present, missing, unanswered
    }

    /// How long a saved library's volume has to answer before launch goes on without it.
    static let timeout: TimeInterval = 1.0

    static func answers(
        for paths: [String],
        timeout: TimeInterval = SavedLibraryProbe.timeout,
        exists: @escaping @Sendable (String) -> Bool = { FileManager.default.fileExists(atPath: $0) },
        late: @escaping @Sendable (_ path: String, _ exists: Bool) -> Void
    ) -> [String: Answer] {
        let asked = Set(paths)
        let state = State()
        let group = DispatchGroup()
        for path in asked {
            group.enter()
            DispatchQueue.global(qos: .userInitiated).async {
                let found = exists(path)
                let inTime = state.record(path, found)
                group.leave()
                if !inTime { late(path, found) }
            }
        }
        _ = group.wait(timeout: .now() + timeout)
        let answered = state.close()
        var result: [String: Answer] = [:]
        for path in asked {
            result[path] = answered[path].map { $0 ? .present : .missing } ?? .unanswered
        }
        return result
    }

    /// The answers so far. Once closed, a new answer is refused, so each path is either in the caller's result or late.
    private final class State: @unchecked Sendable {
        private let lock = NSLock()
        private var answered: [String: Bool] = [:]
        private var closed = false

        func record(_ path: String, _ found: Bool) -> Bool {
            lock.lock()
            defer { lock.unlock() }
            if closed { return false }
            answered[path] = found
            return true
        }

        func close() -> [String: Bool] {
            lock.lock()
            defer { lock.unlock() }
            closed = true
            return answered
        }
    }
}
