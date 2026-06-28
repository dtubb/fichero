import Foundation
import Observation

/// Serial, coalescing runner for autosave-style async work.
///
/// The data-loss bug it prevents (#2536): a flush (blur / tab switch / page
/// nav) that fires *while a save is in flight* must still persist the latest
/// draft. The old code early-returned on an `isSaving` guard and dropped the
/// trailing edit.
///
/// `run` is serial and coalescing:
/// - If no run is in flight, it starts one and loops `work` until no further
///   request arrived (`pending` stays false).
/// - If a run IS in flight, the new call marks the run dirty (`pending`) and
///   awaits it. The in-flight loop then re-invokes `work` once more, so the
///   newest state is persisted before either caller returns. The trailing
///   request is never dropped.
///
/// Correctness rests on `@MainActor` single-threading: the only suspension
/// point inside the loop is `await work()`, so a concurrent `run` can interleave
/// only there — it finds the run still active (and coalesces) or finished (and
/// starts fresh). There is no check-then-act gap.
///
/// `work` owns its own write-skipping (e.g. "encoded == lastSaved → return")
/// so the loop terminates, and its own error handling — the runner never
/// silently substitutes or drops a request.
@MainActor
@Observable
final class CoalescingSaveRunner {
    /// True while a run (including coalesced re-runs) is in flight. Drives UI.
    private(set) var isSaving = false

    @ObservationIgnored private var active: Task<Void, Never>?
    @ObservationIgnored private var pending = false

    func run(_ work: @escaping () async -> Void) async {
        // A run is already in flight — coalesce: mark dirty and await it. The
        // running loop re-invokes `work` because `pending` is set, so the latest
        // state reaches disk before this call returns.
        if let active {
            pending = true
            await active.value
            return
        }

        let task = Task { @MainActor in
            isSaving = true
            defer {
                isSaving = false
                active = nil
            }
            repeat {
                pending = false
                await work()
            } while pending
        }
        active = task
        await task.value
    }
}
