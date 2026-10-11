import Foundation

/// The one way a person's change reaches ⌘Z (`undo.one-path`, #5658): run the change through the
/// generated client, read the audit rows its answer names, and register ONE named step on the
/// window's stack (`WindowSteps`). Undo and redo take those rows back as a set through the engine's
/// set route (`POST /api/actions/audit/undo`); a refusal is shown in the window in the engine's words.
///
/// Only calls a person starts in a window come here: a workflow run, an agent, an App Intent and a
/// background job never register a step (`safety.undo.agents-and-runs-are-not-in-my-stack`).
@MainActor
enum UndoableChange {
    /// Register a change that already ran and named its rows. Nothing is registered without steps
    /// (a surface outside a window) or without rows (nothing to take back).
    @discardableResult
    static func register(
        _ auditIds: [String], named name: String, service: (any UndoSetEngine)?, steps: WindowSteps?,
        afterEach: @escaping @MainActor () async -> Void = {}
    ) -> ActionUndo.Handle? {
        guard let steps, let service else { return nil }
        return steps.register(auditIds, named: name, engine: service, afterEach: afterEach)
    }

    /// Run a person's change and register the rows `auditIds` reads from its answer, as one step.
    /// Undo and Redo in the window wait while it is out (`undo.window.in-flight`).
    @discardableResult
    static func run<Answer>(
        named name: String, service: (any UndoSetEngine)?, steps: WindowSteps?,
        afterEach: @escaping @MainActor () async -> Void = {},
        _ change: () async throws -> Answer, auditIds: (Answer) -> [String]
    ) async throws -> Answer {
        steps?.callStarted()
        defer { steps?.callEnded() }
        let answer = try await change()
        register(auditIds(answer), named: name, service: service, steps: steps, afterEach: afterEach)
        return answer
    }

    /// One audited action by name, as `invokeAction` runs it, registered as one step.
    @discardableResult
    static func invoke<Params: Encodable>(
        _ action: String, params: Params, named name: String,
        service: ActionLibraryService, steps: WindowSteps?,
        afterEach: @escaping @MainActor () async -> Void = {}
    ) async throws -> ActionInvokeResult {
        try await run(named: name, service: service, steps: steps, afterEach: afterEach, {
            try await service.invokeAction(name: action, params: params)
        }, auditIds: { [$0.auditId] })
    }

    /// Several changes as ONE step (`undo.batches`): each runs in turn and the rows they wrote are
    /// registered together after the last, never with a group held open across awaits. A failure
    /// stops the batch; what was written is still one step, named by how many it holds (`named`).
    static func batch<Item>(
        _ items: [Item], named: (Int) -> String,
        service: (any UndoSetEngine)?, steps: WindowSteps?,
        afterEach: @escaping @MainActor () async -> Void = {},
        change: (Item) async throws -> [String]
    ) async throws {
        steps?.callStarted()
        defer { steps?.callEnded() }
        var written: [String] = []
        var count = 0
        defer {
            register(written, named: named(count), service: service, steps: steps, afterEach: afterEach)
        }
        for item in items {
            written += try await change(item)
            count += 1
        }
    }

    /// A step's name, counted (`undo.naming.counts`): "Delete Note", "Delete 3 Items".
    nonisolated static func named(_ verb: String, count: Int, one: String, many: String) -> String {
        count == 1 ? "\(verb) \(one)" : "\(verb) \(count) \(many)"
    }
}
