import Foundation
import Observation

/// An edited line is read again by itself (`segment-actions.automatic-rerun-after-an-edit`, #6069). The edit runner
/// names the lines a shape edit touched; after a pause with no further edit (never while a drag goes on) they are sent
/// once to `POST /api/recipes/project/reread-edited`. A line a paid cloud model read is never run: it is marked, and the
/// person reads it again with the button.
enum SegmentReread {
    /// The lines a call changed the shape of: a move or resize (`segment.update`), a join (the kept line), a cut (the
    /// lines the stroke was drawn across). Any other call changes no shape.
    static func affectedIds(_ call: SegmentEdit.Call) -> [String] {
        switch call.params {
        case .update(let request): return [request.segmentId]
        case .merge(let request): return [request.keepId]
        // ponytail: every line the stroke was offered to, cut or not; the engine's answer does not name the cut ones.
        case .knife(let request): return request.expectedVersions.keys.sorted()
        default: return []
        }
    }

    /// What the page says under a line whose reading is out of date.
    static let staleWords = "Text may be out of date: Read again"
    static let againTitle = "Read Again"
}

/// Which lines are marked out of date, and which re-read failed, for the views that show a line.
@MainActor
@Observable
final class SegmentRereadState {
    static let shared = SegmentRereadState()

    /// Lines whose words came from a paid cloud model and whose shape changed since.
    private(set) var stale: Set<String> = []
    /// A re-read that could not be queued, with the engine's words.
    private(set) var failed: [String: String] = [:]

    func markStale(_ ids: [String]) { stale.formUnion(ids); ids.forEach { failed[$0] = nil } }
    func markFailed(_ ids: [String], _ words: String) { ids.forEach { failed[$0] = words } }
    func clear(_ ids: [String]) { stale.subtract(ids); ids.forEach { failed[$0] = nil } }
}

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
