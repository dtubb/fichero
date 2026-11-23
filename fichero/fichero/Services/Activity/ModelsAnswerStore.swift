import Foundation

/// The one reader of the engine's models answer (`GET /api/activity/models`), shared by the Activity pane's Models tree and the
/// Models & Cluster window (#6588): one ten-second poll of each library however many panes show it, and a new answer is
/// kept only when it differs from the last, so an unchanged answer redraws nothing.
@MainActor @Observable
final class ModelsAnswerStore {
    static let shared = ModelsAnswerStore()

    private(set) var answers: [UUID: ActivityModelsAnswer] = [:]
    /// The newest read failure, nil after a read that worked.
    private(set) var failure: String?
    private var viewers = 0
    private var poller: Task<Void, Never>?

    /// The answers of these libraries as one, the models merged.
    func answer(for libraryIds: [UUID]) -> ActivityModelsAnswer {
        ActivityModelsAnswer.merged(libraryIds.compactMap { answers[$0] })
    }

    /// Keeps `answer` for the library; false (and nothing redrawn) when it is the answer already held.
    @discardableResult
    func record(_ answer: ActivityModelsAnswer, for libraryId: UUID) -> Bool {
        guard answers[libraryId] != answer else { return false }
        answers[libraryId] = answer
        return true
    }

    /// Reads while a pane shows: the first watcher starts the poll, the last to leave stops it. Returns when cancelled.
    func watch(_ manager: LibraryManager) async {
        viewers += 1
        if poller == nil { poller = Task { await poll(manager) } }
        defer {
            viewers -= 1
            if viewers == 0 { poller?.cancel(); poller = nil }
        }
        while !Task.isCancelled { try? await Task.sleep(for: .seconds(3600)) }
    }

    private func poll(_ manager: LibraryManager) async {
        while !Task.isCancelled {
            var references = manager.openLibraries
            if let global = manager.globalLibrary, !references.contains(where: { $0.id == global.id }) { references.append(global) }
            var failed: String?
            for library in references {
                do { record(try await library.activityService.models(), for: library.id) } catch { failed = error.localizedDescription }
            }
            if failure != failed { failure = failed }
            try? await Task.sleep(for: .seconds(10))
        }
    }
}
