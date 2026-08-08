import Foundation

/// Coalesces concurrent async loads of the same key into ONE operation.
///
/// Why (#4572, measured 2026-08-08): every thumbnail in the engine log was
/// fetched exactly TWICE — two surfaces asked for the same image before
/// either had cached it, both missed, both fetched. Memoising the RESULT
/// (the caches) cannot fix a race that happens before the first result
/// exists; memoising the IN-FLIGHT TASK does.
///
/// MainActor-bound on purpose: every caller (the stores and services) is
/// MainActor, so the bookkeeping dictionary needs no locking, and the
/// operation itself is free to hop executors (network, detached decode).
/// The first caller's task is shared; when it finishes — success or error —
/// the slot clears, so a FAILED load does not poison later retries.
@MainActor
final class InFlightCoalescer<Value: Sendable> {
    private var inFlight: [String: Task<Value, Error>] = [:]

    /// How many loads were absorbed by an existing in-flight task — the
    /// direct measure of the #4572 duplication this removes.
    private(set) var coalescedCount = 0

    func run(_ key: String, operation: @escaping @MainActor () async throws -> Value) async throws -> Value {
        if let existing = inFlight[key] {
            coalescedCount += 1
            return try await existing.value
        }
        let task = Task { try await operation() }
        inFlight[key] = task
        defer { inFlight[key] = nil }
        return try await task.value
    }
}
