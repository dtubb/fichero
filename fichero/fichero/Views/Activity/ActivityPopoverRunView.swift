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
                // "Read · 27 of 92": the stage by Set Up's name, and its count (#5666, #5670).
                Text(stage.total > 0 ? "\(stage.title) · \(stage.done) of \(stage.total)" : stage.title)
                    .font(.caption.monospacedDigit())
                    .lineLimit(1)
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

/// A live block of the engine's summary in the popover (`activity.popover.same-summary`, #5852): "Recipe › Stage ›
/// Workflow" over "7 of 20 pages · 2 of 8 folders". A waiting block has no spinner and says what it waits for.
struct ActivityPopoverBlockView: View {
    let block: ActivityPopoverSummary.Block

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Label(block.title, systemImage: block.waiting == nil ? "play.circle.fill" : "hourglass")
                .font(.callout.weight(.semibold))
                .lineLimit(2)
            Text(block.counts)
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
            if let waiting = block.waiting, !waiting.isEmpty {
                Text("Waiting: \(waiting)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("activity.popover.block")
    }
}

/// The popover's errors (#5666, Daniel 2026-10-11): ONE line each, its job and the cause's first sentence,
/// truncated; the whole in the tooltip; the row opens Activity's details for that job. At most three, recent only.
struct ActivityPopoverErrorRows: View {
    let summary: ActivityPopoverSummary
    let openDetails: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            ForEach(summary.recentErrors) { item in
                Button { openDetails(item.id) } label: {
                    HStack(spacing: 5) {
                        Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.red)
                        Text(ActivityPopoverSummaryView.oneLine(item))
                            .lineLimit(1)
                            .truncationMode(.tail)
                    }
                    .font(.caption)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .help([item.name, item.fullText ?? item.detail ?? ""].filter { !$0.isEmpty }.joined(separator: ": "))
                .accessibilityIdentifier("activity.popover.error.\(item.id)")
            }
            if summary.errorCount > summary.recentErrors.count {
                Text("And \(summary.errorCount - summary.recentErrors.count) more in the Activity window.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("activity.popover.errors")
    }
}

/// A job running outside a recipe run: its name and count on one line, "Embedding pages · 42 of 100", over a small
/// bar of its own (#5666).
struct ActivityPopoverRunningRow: View {
    let item: ActivityPopoverSummary.Item

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(ActivityPopoverRunningRow.label(item)).font(.caption).lineLimit(1)
            if item.total > 0 {
                ProgressView(value: Double(min(item.done, item.total)), total: Double(item.total))
                    .controlSize(.small)
            } else {
                ProgressView().controlSize(.small)
            }
        }
        .accessibilityElement(children: .combine)
    }

    /// "Read · 27 of 92": the name, then the count when there is one, else what it is doing.
    static func label(_ item: ActivityPopoverSummary.Item) -> String {
        if item.total > 0 { return "\(item.name) · \(item.done) of \(item.total)" }
        return [item.name, item.detail].compactMap { $0 }.joined(separator: " · ")
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
                                  detail: "A page could not be read: the image is damaged.",
                                  fullText: "A page could not be read: the image is damaged. 12 pages of this kind.")]
    return VStack(alignment: .leading, spacing: 10) {
        ActivityPopoverRunView(run: run)
        ActivityPopoverErrorRows(summary: summary, openDetails: { _ in })
    }
    .padding()
    .frame(width: 320)
}
