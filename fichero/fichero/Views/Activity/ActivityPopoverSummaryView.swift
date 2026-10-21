import FicheroAPIClient
import SwiftUI

/// The popover's summary, drawn: running now, waiting and why, the last
/// errors with their reasons, and what holds heavy work back.
struct ActivityPopoverSummaryView: View {
    let summary: ActivityPopoverSummary
    /// A failure's row was pressed: open Activity's details for that job.
    var openDetails: (String) -> Void = { _ in }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(summary.blocks) { block in
                ActivityPopoverBlockView(block: block)
            }
            // A run the engine's summary already shows as a block is not said twice.
            ForEach(summary.runs.filter { run in !summary.blocks.contains { $0.id == run.id } }) { run in
                ActivityPopoverRunView(run: run)
            }
            ForEach(summary.background) { line in
                Label(line.waiting.map { "\(line.text) · \($0)" } ?? line.text,
                      systemImage: line.waiting == nil ? "arrow.triangle.2.circlepath" : "clock")
                    .font(.callout)
                    .foregroundStyle(line.waiting == nil ? AnyShapeStyle(.primary) : AnyShapeStyle(.secondary))
                    .accessibilityIdentifier("activity.popover.background")
            }
            ForEach(summary.running) { item in
                ActivityPopoverRunningRow(item: item)
            }
            if summary.waitingCount > 0 {
                Label(waitingText, systemImage: "clock")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            if let heldBack = summary.heldBack {
                Label(heldBack, systemImage: "tortoise")
                    .font(.callout)
                    .foregroundStyle(.orange)
                    .accessibilityIdentifier("activity.popover.heldBack")
            }
            if !summary.macReadings.isEmpty {
                ActivityMacStateRow(readings: summary.macReadings)
            }
            if summary.errorCount > 0 {
                // One line each, at most three, recent only (#5666): errors never crowd out the work in hand.
                ActivityPopoverErrorRows(summary: summary, openDetails: openDetails)
            }
        }
    }

    /// An error's name and reason, whichever it has.
    private static func words(_ item: ActivityPopoverSummary.Item) -> [String] {
        [item.name, item.detail ?? ""].filter { !$0.isEmpty }
    }

    /// "Detect Regions: Kraken not installed", truncated to one line.
    static func oneLine(_ item: ActivityPopoverSummary.Item) -> String {
        words(item).joined(separator: ": ")
    }

    private var waitingText: String {
        let jobs = "\(summary.waitingCount) waiting"
        guard let reason = summary.waitingReason else { return jobs }
        return "\(jobs): \(reason)"
    }
}

#Preview("Popover summary") {
    ActivityPopoverSummaryView(
        summary: ActivityPopoverSummary(
            jobs: [
                ActivityJob(id: "1", name: "Embedding pages", current: 42, total: 100, state: .running),
                ActivityJob(id: "2", name: "Kraken pages", total: 12, state: .waiting, reason: "Waiting: memory is tight"),
                ActivityJob(id: "3", taskType: "workflow", name: "Detect Regions", state: .failed,
                            reason: "Kraken not installed")
            ],
            paused: false,
            machine: Components.Schemas.MachineState(memoryPressure: .warn, thermalState: .fair, onBattery: true,
                                  inUse: true, whyWait: "memory is tight"),
            processCpuPercent: 2, cpuCount: 8
        )
    )
    .padding()
    .frame(width: 300)
}
