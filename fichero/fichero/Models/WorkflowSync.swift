import Foundation

/// Decides how a window's locally-edited `Workflow` reconciles with a freshly
/// re-fetched server definition when the change stream reports a `workflow.*`
/// change (#2278, Observable Data Layer).
///
/// Pure and view-free so the reconcile rule is unit-testable without a live
/// backend or ViewInspector — the view just applies the returned decision.
///
/// **Why a baseline instead of trusting the event origin:** workflow writes go
/// through the generated client, not the audited action layer, so they carry no
/// `X-Fichero-Origin-Window` tag — the change stream can't drop this window's
/// own echo. So we can't tell "someone else edited" from "our own save came
/// back" at the event level. The `baseline` (last value we loaded or that the
/// server confirmed) closes that gap: if the local copy still equals the
/// baseline it has no unsaved edits and is safe to overwrite; if it has drifted,
/// there are local edits we must not clobber.
enum WorkflowSync {

    /// The reconcile outcome for the active editing target.
    enum Decision: Equatable {
        /// A foreign change arrived and we have no unsaved local edits — adopt
        /// it. The caller sets `editingWorkflow` AND the baseline to `workflow`.
        case apply(Workflow)
        /// The server already matches our local copy (typically our own save
        /// echoing back). Nothing to re-render; just advance the baseline so a
        /// later genuine foreign edit is recognised. Caller updates the baseline
        /// only, leaving `editingWorkflow` untouched.
        case advanceBaseline(Workflow)
        /// The local copy has unsaved edits (drifted from the baseline) and the
        /// server differs — leave the local edits alone (last-writer-wins is
        /// resolved when they autosave). Caller does nothing.
        case skip
    }

    /// - Parameters:
    ///   - remote: the definition just re-fetched from `WorkflowStore`.
    ///   - local: the window's current `editingWorkflow`.
    ///   - baseline: the last value this window loaded or the server confirmed
    ///     (`nil` before any baseline is established).
    static func decide(remote: Workflow, local: Workflow, baseline: Workflow?) -> Decision {
        // A change to a different workflow than the one open here is not ours to
        // reconcile.
        guard remote.id == local.id else { return .skip }
        // Server matches us — advance the baseline (self-corrects it after our
        // own saves echo back), no re-render.
        if remote == local { return .advanceBaseline(remote) }
        // Clean (no unsaved edits) and the server moved → adopt the foreign copy.
        if let baseline, local == baseline { return .apply(remote) }
        // Unsaved local edits (or no baseline yet) → never clobber.
        return .skip
    }
}
