import Foundation

/// Collects edited line ids and sends them once, `delay` after the last edit.
@MainActor
final class SegmentRereadScheduler {
    private let delay: Duration
    private let send: @MainActor ([String]) async -> Void
    private var pending: [String] = []
    private var task: Task<Void, Never>?

    init(delay: Duration = .seconds(2), send: @escaping @MainActor ([String]) async -> Void) {
        self.delay = delay
        self.send = send
    }

    func note(_ ids: [String]) {
        guard !ids.isEmpty else { return }
        for id in ids where !pending.contains(id) { pending.append(id) }
        task?.cancel()
        task = Task { [delay] in
            try? await Task.sleep(for: delay)
            guard !Task.isCancelled else { return }
            let ids = pending
            pending = []
            await send(ids)
        }
    }
}
