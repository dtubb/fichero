import Foundation

/// COMPARE as first-class grammar (Daniel, 2026-08-30, reading-markup-coding
/// design item 6): run the ONE staged step once per configured model, so the
/// same page read by every model can be judged side by side. This file is the
/// pure half — which models the fan-out targets and what stamps the runs as
/// comparable — with no SwiftUI in it, so it is tested without a window.

/// One run of the fan-out: the staged step, pinned to this model.
struct WorkflowCompareRun: Equatable, Identifiable {
    /// The model id is the run's identity — the fan-out list is deduped by
    /// it, so it cannot collide.
    var id: String { model }
    let provider: String
    let model: String
    /// What the confirmation lists — the same "model · tier" line the
    /// per-step pin menu shows, so both surfaces name a model identically.
    let label: String
}

/// Per-model progress of a dispatched fan-out, shown the way chain steps show
/// theirs: one sub-state per model, coloured by the same lifecycle.
struct WorkflowCompareRunProgress: Identifiable, Equatable {
    /// The model being run.
    let id: String
    /// Short model name for the capsule.
    let label: String
    var state: StagedStepState = .pending
}

enum WorkflowComparePlanner {

    /// The fan-out "Compare models…" would dispatch, or nil when comparing
    /// makes no sense here:
    /// - the chain must hold exactly ONE step — comparing an N-step chain
    ///   would be N×M runs whose outputs nothing can line up;
    /// - a tool that never calls an LLM has no model to vary;
    /// - fewer than two distinct models is not a comparison.
    /// Per-step overrides are deliberately ignored: the point of the fan-out
    /// is that the MODEL is the variable, so every run starts from the same
    /// step with only the pin differing.
    static func fanOut(
        staged: [StagedWorkflowStep],
        choices: [WorkflowBarModelChoice]
    ) -> [WorkflowCompareRun]? {
        guard staged.count == 1, let step = staged.first else { return nil }
        if case .tool(_, _, _, let usesLLM) = step.kind, !usesLLM { return nil }
        var seen = Set<String>()
        let runs = choices.compactMap { choice -> WorkflowCompareRun? in
            guard !choice.model.isEmpty, seen.insert(choice.model).inserted else { return nil }
            return WorkflowCompareRun(
                provider: choice.provider, model: choice.model, label: choice.label
            )
        }
        return runs.count >= 2 ? runs : nil
    }

    /// One fresh group id per dispatch. Every run of the fan-out carries it
    /// as `inputs["compare_group"]`, which is what lets the reader's compare
    /// representation find the sibling artifacts later — same group, one
    /// model each. The engine ignores unknown inputs today; the sibling lane
    /// reads this key.
    static func freshGroupId() -> String {
        UUID().uuidString
    }
}

/// The run-inputs payload, assembled in ONE place so the compare-group
/// stamping and the framing line cannot drift between call sites — and so the
/// assembly is testable without an engine.
enum WorkflowRunInputs {
    static func build(
        docIds: [String],
        userContext: String,
        artifactTypeHint: String?,
        artifactStepNameHint: String?,
        compareGroup: String?
    ) -> [String: Any] {
        var inputs: [String: Any] = ["selected_doc_ids": docIds]
        // The window's framing line rides every run (Daniel, 2026-08-30).
        let framing = userContext.trimmingCharacters(in: .whitespacesAndNewlines)
        if !framing.isEmpty { inputs["user_context"] = framing }
        if let artifactTypeHint, !artifactTypeHint.isEmpty {
            inputs["artifact_type"] = artifactTypeHint
        }
        if let artifactStepNameHint, !artifactStepNameHint.isEmpty {
            inputs["step_name"] = artifactStepNameHint
        }
        if let compareGroup, !compareGroup.isEmpty {
            inputs["compare_group"] = compareGroup
        }
        return inputs
    }
}


/// Transient window-chrome UX state, boxed off ContentView's value (see the
/// ViewValueSizeTests ceiling): the Save Workspace prompt and the compare
/// fan-out's cost/progress. One reference on the view; mutations observe.
@MainActor
@Observable
final class WindowChromeUXState {
    var showSaveWorkspacePrompt = false
    var workspaceNameDraft = ""
    /// Upper-bound cost of a "Compare models…" fan-out over the one staged
    /// step — every configured model priced and summed (Daniel, 2026-08-30).
    var stagedCompareCostCeiling: Double?
    /// Per-model progress of the running (or last) compare fan-out. Cleared
    /// when a fan-out dispatches or a plain chain run starts.
    var compareRunProgress: [WorkflowCompareRunProgress] = []
}
