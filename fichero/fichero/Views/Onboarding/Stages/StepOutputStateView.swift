import SwiftUI

/// The output column's one state line (`wide.output.four-states`, #5668): not tried, running, done, or failed, never an empty column.
/// A stale result is dimmed and says so (`StepOutputState.staleWords`) beside Run this step, which starts only this stage's steps
/// (`POST /api/recipes/project/start {steps}`, `wide.output.run-this-step`). The words are the model's; this lays them out.
struct StepOutputStateView: View {
    let state: StepOutputState
    /// Run this step; nil where the stage has no step of its own to run.
    var runThisStep: (() -> Void)?
    var stop: (() -> Void)?

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            switch state {
            case .notTried(let line):
                Text(line).font(.callout).foregroundStyle(.secondary)
            case .running(let words):
                ProgressView().controlSize(.small)
                Text(words).font(.callout).foregroundStyle(.secondary)
                if let stop { Button("Stop", action: stop).controlSize(.small) }
            case .done(let stale):
                if stale {
                    Label(StepOutputState.staleWords, systemImage: "clock.arrow.circlepath").font(.callout).foregroundStyle(.secondary)
                    if let runThisStep { Button("Run This Step", action: runThisStep).controlSize(.small) }
                }
            case .failed(let words):
                Label(words, systemImage: "exclamationmark.triangle").font(.callout).foregroundStyle(.orange)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("setup.output.state")
    }

    /// A stale result is shown dimmed, never as current.
    static func opacity(of state: StepOutputState) -> Double {
        if case .done(true) = state { return 0.5 }
        return 1
    }
}

#Preview("Output states") {
    VStack(alignment: .leading, spacing: 12) {
        StepOutputStateView(state: .notTried(line: "Try on these 5 pages, about 2 minutes, free on this Mac"))
        StepOutputStateView(state: .running(words: "Page 2 of 5"), stop: {})
        StepOutputStateView(state: .done(stale: true), runThisStep: {})
        StepOutputStateView(state: .failed(words: "No model on this Mac does this yet"))
    }
    .padding().frame(width: 420)
}
