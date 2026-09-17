import Foundation

/// Some (but not all) rows in a bulk delete failed. The store has already pruned the
/// ones that succeeded; the caller can reload to reconcile the rest.
enum BulkDeleteError: Error {
    case partial(deleted: Int, requested: Int)
}

// MARK: - Bounded bulk delete (spec: kg-tables `kg.scale.bulk-correctness`)

/// Deletes many rows with BOUNDED concurrency and returns exactly the ids that
/// SUCCEEDED — so a partial failure prunes only what was really removed and never
/// leaves an already-deleted row visible (the drift bug in the old sequential loop),
/// and 1000 deletes never open 1000 sockets at once (user-machine-always-useful).
///
/// This is the interim client fix until a real batch-delete endpoint lands (#4643):
/// it hides per-request latency behind a small window without a server change. The
/// window processes ids in waves of `maxConcurrent`.
///
/// `nonisolated` with a `@Sendable` op: a `@MainActor` service is itself Sendable, so a
/// caller's closure can capture it and `await` its methods here (the delete hops to the
/// MainActor and back). Keeping the helper off the MainActor avoids the region-isolation
/// checker's rejection of a MainActor closure inside a task group.
enum BulkDelete {
    static func succeeding(
        ids: [String],
        maxConcurrent: Int = 8,
        _ delete: @Sendable @escaping (String) async -> Bool
    ) async -> [String] {
        var succeeded: [String] = []
        for wave in ids.chunked(into: max(1, maxConcurrent)) {
            await withTaskGroup(of: (String, Bool).self) { group in
                for id in wave {
                    group.addTask { (id, await delete(id)) }
                }
                for await (id, deleted) in group where deleted {
                    succeeded.append(id)
                }
            }
        }
        return succeeded
    }
}

extension Array {
    /// Split into consecutive slices of at most `size` (the last may be shorter).
    /// Pure; `size <= 0` yields a single chunk (callers pass a positive window).
    func chunked(into size: Int) -> [[Element]] {
        guard size > 0 else { return isEmpty ? [] : [self] }
        return stride(from: 0, to: count, by: size).map {
            Array(self[$0..<Swift.min($0 + size, count)])
        }
    }
}
