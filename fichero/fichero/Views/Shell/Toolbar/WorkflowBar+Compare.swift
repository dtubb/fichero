import SwiftUI

/// The COMPARE affordance (Daniel, 2026-08-30, reading-markup-coding design
/// item 6): when the chain holds exactly one step, run it once per configured
/// model so the outputs can be judged side by side. Kept beside the run
/// controls because it IS a run control — the sentence stays "With [target],
/// use [model] to [step]"; compare merely substitutes EVERY model for [model].
extension WorkflowBar {

    /// The fan-out this bar could dispatch right now, or nil when comparing
    /// makes no sense (multi-step chain, non-LLM tool, fewer than two models).
    private var compareFanOut: [WorkflowCompareRun]? {
        WorkflowComparePlanner.fanOut(staged: staged, choices: modelChoices)
    }

    /// The "Compare models…" control. A fan-out is N paid calls, so the
    /// button never dispatches directly — it opens a confirmation naming the
    /// models and the cost ceiling, and only the confirmation's own button
    /// runs anything.
    @ViewBuilder
    var compareItem: some View {
        if let runs = compareFanOut, onRunCompare != nil, target != .nothing {
            Button { showsCompareConfirmation = true } label: {
                Image(systemName: "square.on.square")
                    .font(.body)
                    .foregroundStyle(Color.accentColor)
            }
            .buttonStyle(.plain)
            .help("Compare models — run this step once per configured model (\(runs.count) runs)")
            .accessibilityLabel("Compare models")
            .popover(isPresented: $showsCompareConfirmation, arrowEdge: .bottom) {
                compareConfirmation(runs: runs)
            }
        }
    }

    /// The confirmation: what will run, on what, with which models, for at
    /// most how much. Dispatch mints the fresh compare-group id — one per
    /// press, shared by every run it starts.
    @ViewBuilder
    private func compareConfirmation(runs: [WorkflowCompareRun]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Compare models")
                .font(.headline)
            if let step = staged.first {
                let subject = targetDetail
                    ?? WorkflowBarPolicy.targetLabel(target)
                    ?? "the selection"
                Text("Runs “\(step.displayName)” once per model on \(subject).")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            VStack(alignment: .leading, spacing: 3) {
                ForEach(runs) { run in
                    Label(run.label, systemImage: "cpu")
                        .font(.caption)
                }
            }
            // Priced as a CEILING like the chain's own estimate — and when it
            // cannot be priced, it says so rather than reading as free.
            if let compareCostCeiling {
                Text("est. ≤ \(compareCostCeiling, format: .currency(code: "USD")) for all \(runs.count) runs")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            } else {
                Text("Cost cannot be estimated for this step — each run is still a paid call.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            HStack {
                Spacer()
                Button("Cancel") { showsCompareConfirmation = false }
                Button("Run \(runs.count) models") {
                    showsCompareConfirmation = false
                    onRunCompare?(runs, WorkflowComparePlanner.freshGroupId())
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(14)
        .frame(width: 320)
    }

    /// Per-model progress, drawn the way chain chips draw theirs: one capsule
    /// per model, coloured by the same lifecycle. Deliberately NOT a second
    /// chip system — a capsule with a name and a state is all a fan-out needs.
    var compareProgressRow: some View {
        HStack(spacing: 6) {
            Spacer(minLength: 0)
            Text("Comparing:")
                .font(.caption2)
                .foregroundStyle(.secondary)
            ForEach(compareProgress) { run in
                HStack(spacing: 3) {
                    if run.state == .running {
                        ProgressView().controlSize(.mini).scaleEffect(0.55)
                    }
                    Text(run.label)
                        .font(.system(size: 10, weight: .medium))
                    if let symbol = compareStateSymbol(run.state) {
                        Image(systemName: symbol).font(.system(size: 8))
                    }
                }
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
                .background(compareStateBackground(run.state), in: Capsule())
                .foregroundStyle(compareStateForeground(run.state))
                .help("\(run.label) — \(compareStateWord(run.state))")
            }
            Spacer(minLength: 0)
        }
        .frame(height: 28)
    }

    // Same colour vocabulary as the chain chips, so half-finished reads as
    // half-finished in both rows.
    private func compareStateBackground(_ state: StagedStepState) -> Color {
        switch state {
        case .pending:   return Color.accentColor.opacity(0.12)
        case .running:   return Color.accentColor.opacity(0.30)
        case .succeeded: return Color.green.opacity(0.20)
        case .failed:    return Color.red.opacity(0.20)
        }
    }

    private func compareStateForeground(_ state: StagedStepState) -> Color {
        switch state {
        case .succeeded: return .green
        case .failed:    return .red
        default:         return .primary
        }
    }

    private func compareStateSymbol(_ state: StagedStepState) -> String? {
        switch state {
        case .succeeded: return "checkmark"
        case .failed:    return "exclamationmark.triangle"
        default:         return nil
        }
    }

    private func compareStateWord(_ state: StagedStepState) -> String {
        switch state {
        case .pending:   return "waiting to run"
        case .running:   return "running"
        case .succeeded: return "succeeded"
        case .failed:    return "failed"
        }
    }
}
