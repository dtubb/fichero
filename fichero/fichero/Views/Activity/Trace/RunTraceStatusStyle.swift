import SwiftUI

// MARK: - Run status vocabulary (#4284)
//
// Colour, icon and words for one step's outcome, in one place so the canvas
// card, its popover and VoiceOver can never disagree about what a step did.
// Split from RunTraceView to keep that file inside the 400-line limit.

/// One place where a run status becomes colour, icon and words, so the canvas
/// card, its popover and VoiceOver can never disagree about what a step did.
enum RunTraceStatusStyle {
    static func color(for status: RunTraceNodeStatus) -> Color {
        switch status {
        case .success: return .green
        case .producedNothing: return .yellow
        case .failed: return .red
        case .cancelled: return .purple
        case .running: return .blue
        case .skipped: return .orange
        case .pending: return .gray
        }
    }

    static func icon(for status: RunTraceNodeStatus) -> String {
        switch status {
        case .success: return "checkmark"
        // An empty tray, not a warning: the step worked, the result was empty.
        case .producedNothing: return "tray"
        case .failed: return "xmark"
        case .cancelled: return "stop.fill"
        case .running: return "play.fill"
        case .skipped: return "arrow.uturn.forward"
        case .pending: return "circle.dashed"
        }
    }

    /// The words shown on the node card. `nil` for states the card already
    /// reads unambiguously — a green tick and a spinner need no caption.
    static func note(for status: RunTraceNodeStatus) -> String? {
        switch status {
        case .success, .running: return nil
        case .producedNothing: return "produced nothing"
        case .failed: return "failed"
        case .cancelled: return "cancelled"
        case .skipped: return "skipped"
        case .pending: return "did not run"
        }
    }

    /// What an empty artifact list MEANS for this status. Never just
    /// "No artifacts" — that sentence is true of a step that never started
    /// and of a step that ran and found nothing, and those need different
    /// responses from the reader.
    static func emptyArtifactsText(for status: RunTraceNodeStatus) -> String {
        switch status {
        case .producedNothing: return "Ran and produced nothing"
        case .pending: return "This step did not run"
        case .failed: return "Failed before producing anything"
        case .cancelled: return "Cancelled before producing anything"
        case .skipped: return "Skipped — nothing to produce"
        case .running: return "Still running"
        case .success: return "No artifacts recorded for this step"
        }
    }

    static func accessibilityText(for status: RunTraceNodeStatus) -> String {
        switch status {
        case .success: return "completed"
        // Spelled out: "completed" alone would let a screen reader imply
        // output exists when none does.
        case .producedNothing: return "completed, produced nothing"
        case .failed: return "failed"
        case .cancelled: return "cancelled"
        case .running: return "running"
        case .skipped: return "skipped"
        case .pending: return "did not run"
        }
    }
}

/// Step detail for one trace node: tool, provider/model actually used,
/// duration, output artifacts, and error text for failed nodes.
struct RunTraceNodeDetail: View {
    let node: RunTraceNode
    let artifacts: [WorkflowRunArtifact]
    /// Model-call episodes recorded under THIS node (#22): the full
    /// prompt/output/thinking exchange. Empty for pre-ledger runs.
    var episodes: [WorkflowEpisode] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(node.label)
                .font(.headline)

            Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 4) {
                GridRow {
                    Text("Tool").foregroundStyle(.secondary)
                    Text(node.tool)
                }
                if let providerModel = node.providerModelText {
                    GridRow {
                        Text("Model").foregroundStyle(.secondary)
                        Text(providerModel).textSelection(.enabled)
                    }
                }
                if let duration = node.durationMs {
                    GridRow {
                        Text("Duration").foregroundStyle(.secondary)
                        Text(RunTraceFormat.duration(ms: duration)).monospacedDigit()
                    }
                }
                if let skipReason = node.skipReason {
                    GridRow {
                        Text("Skipped").foregroundStyle(.secondary)
                        Text(skipReason)
                    }
                }
                // #4343 seam: when per-step tokens/cost lands in the
                // timeline, add a "Cost" GridRow here beside Duration.
            }
            .font(.caption)

            if let error = node.error {
                DisclosureGroup {
                    ScrollView {
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(.red)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .frame(maxHeight: 120)
                } label: {
                    Label("Error", systemImage: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }

            Divider()

            if artifacts.isEmpty {
                // Say which kind of emptiness this is. An artifact list that
                // is simply absent reads as "nothing happened"; only the step
                // record can tell the reader whether the step ran at all.
                Label(
                    RunTraceStatusStyle.emptyArtifactsText(for: node.status),
                    systemImage: RunTraceStatusStyle.icon(for: node.status)
                )
                .font(.caption)
                .foregroundStyle(RunTraceStatusStyle.color(for: node.status))
            } else {
                Text("Artifacts")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                ForEach(artifacts) { artifact in
                    RunArtifactRow(artifact: artifact)
                }
            }

            if !episodes.isEmpty {
                Divider()
                Text("Model Calls")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                ForEach(episodes) { episode in
                    RunEpisodeRow(episode: episode)
                }
            }
        }
        .padding(12)
        .frame(minWidth: 240, maxWidth: 340, alignment: .leading)
    }
}

/// One recorded model call: identity line, then the FULL exchange behind a
/// disclosure — prompt, output, thinking, verbatim and selectable (#22: what
/// the model actually saw and said, never a paraphrase).
struct RunEpisodeRow: View {
    let episode: WorkflowEpisode

    var body: some View {
        DisclosureGroup {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    exchangeSection("System", text: episode.system)
                    exchangeSection("Prompt", text: episode.prompt)
                    exchangeSection("Thinking", text: episode.thinking)
                    exchangeSection("Output", text: episode.output)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxHeight: 260)
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "brain")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(episode.modelText ?? "model not recorded")
                    .font(.caption)
                if let useCase = episode.useCase {
                    Text(useCase)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 4)
                if let millis = episode.durationMs {
                    Text(RunTraceFormat.duration(ms: Double(millis)))
                        .font(.caption2)
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    @ViewBuilder
    private func exchangeSection(_ title: String, text: String?) -> some View {
        if let text, !text.isEmpty {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(text)
                    .font(.caption)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
}
