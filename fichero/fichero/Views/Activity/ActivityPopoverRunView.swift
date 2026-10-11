import SwiftUI

/// A recipe run in the Activity popover (#5666): the run as a header and its stages under it, each with its own
/// bar of pages done, so "Transcribe (Kraken) 36 of 91" reads as a stage of the run, never as a job beside it.
/// A stage waiting on the model lane, or on memory, says so in words.
struct ActivityPopoverRunView: View {
    let run: ActivityPopoverSummary.Run

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(run.name, systemImage: "list.bullet.rectangle")
                .font(.callout.weight(.semibold))
                .lineLimit(2)
            if let waiting = run.waiting, !waiting.isEmpty {
                Label(waiting, systemImage: "hourglass")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            ForEach(run.stages) { stage in
                stageRow(stage)
            }
        }
        .padding(.leading, 2)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("activity.popover.run")
    }

    private func stageRow(_ stage: ActivityPopoverStage) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                Image(systemName: symbol(stage))
                    .foregroundStyle(stage.isFailed ? AnyShapeStyle(.red) : AnyShapeStyle(.secondary))
                    .frame(width: 14)
                Text(stage.title).font(.caption).lineLimit(1)
                Spacer(minLength: 4)
                if stage.total > 0 {
                    Text("\(stage.done) of \(stage.total)")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }
            if stage.total > 0 {
                ProgressView(value: Double(min(stage.done, stage.total)), total: Double(stage.total))
                    .controlSize(.small)
                    .tint(stage.isFailed ? .red : .accentColor)
                    .padding(.leading, 20)
            }
            if !stage.isRunning || stage.state.hasPrefix("Waiting") {
                Text(stage.state)
                    .font(.caption2)
                    .foregroundStyle(stage.isFailed ? AnyShapeStyle(.red) : AnyShapeStyle(.secondary))
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.leading, 20)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func symbol(_ stage: ActivityPopoverStage) -> String {
        if stage.isFailed { return "exclamationmark.triangle.fill" }
        if stage.isRunning { return stage.state.hasPrefix("Waiting") ? "hourglass" : "play.circle.fill" }
        if stage.state == "Done" { return "checkmark.circle.fill" }
        return "circle.dotted"
    }
}

/// The popover's errors as a count that opens their detail (#5666): a red badge, "2 errors", and when opened
/// each error wrapped, by name and in words (no file paths), never a red line running past the popover's edge.
struct ActivityPopoverErrorsBadge: View {
    let summary: ActivityPopoverSummary
    @State private var isOpen = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button {
                isOpen.toggle()
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "exclamationmark.triangle.fill")
                    Text(summary.errorCount == 1 ? "1 error" : "\(summary.errorCount) errors")
                    Image(systemName: isOpen ? "chevron.up" : "chevron.down").font(.caption2)
                }
                .font(.caption.weight(.semibold))
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(Capsule().fill(Color.red.opacity(0.15)))
                .foregroundStyle(.red)
            }
            .buttonStyle(.plain)
            .help(isOpen ? "Hide the errors" : "Show the errors")
            .accessibilityIdentifier("activity.popover.errorBadge")
            if isOpen {
                ForEach(summary.recentErrors) { item in
                    VStack(alignment: .leading, spacing: 1) {
                        Text(item.name).font(.caption.weight(.semibold))
                        if let detail = item.detail, !detail.isEmpty {
                            Text(detail).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    .help(ActivityPopoverSummaryView.oneLine(item))
                }
                if summary.errorCount > summary.recentErrors.count {
                    Text("And \(summary.errorCount - summary.recentErrors.count) more in the Activity window.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("activity.popover.errors")
    }
}

#Preview("A recipe run with its stages, and an error") {
    let run = ActivityPopoverSummary.Run(
        id: "r1", name: "Transcribe the Mosquera box", waiting: nil,
        stages: [
            .init(id: "s1", title: "Find lines", state: "Done", done: 91, total: 91, isRunning: false, isFailed: false),
            .init(id: "s2", title: "Transcribe (Kraken)", state: "Running", done: 36, total: 91,
                  isRunning: true, isFailed: false),
            .init(id: "s3", title: "Correct", state: "Waiting: the model lane", done: 0, total: 91,
                  isRunning: true, isFailed: false),
            .init(id: "s4", title: "Write a kept export", state: "Waiting for the stage before it", done: 0, total: 0,
                  isRunning: false, isFailed: false)
        ]
    )
    var summary = ActivityPopoverSummary(jobs: [], paused: false)
    summary.errorCount = 1
    summary.recentErrors = [.init(id: "e1", name: "Transcribe (Kraken)",
                                  detail: ActivityPopoverSummary.worded("Could not read …_Recto.JPG: the image is damaged"))]
    return VStack(alignment: .leading, spacing: 10) {
        ActivityPopoverRunView(run: run)
        ActivityPopoverErrorsBadge(summary: summary)
    }
    .padding()
    .frame(width: 320)
}
