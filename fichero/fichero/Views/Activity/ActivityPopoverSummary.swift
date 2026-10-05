import FicheroAPIClient
import SwiftUI

/// What the toolbar's Activity popover says (`activity.popover.summary`,
/// #5415): a summary, not a list. What is running now, how much is waiting
/// and the main reason, the last three errors with why, and whether heavy
/// work is held back and why, and this Mac's state (memory pressure, heat,
/// battery, in use). Built from the one jobs read (`ActivityStore.backgroundJobs`
/// and `.machine`, `GET /api/activity/jobs`) and the window's own live runs,
/// so it cannot disagree with the Activity window. The GPU is not read yet (#5415).
struct ActivityPopoverSummary: Equatable {
    struct Item: Equatable, Identifiable {
        let id: String
        let name: String
        /// A running item's step or counts; a failed item's reason.
        let detail: String?
    }

    /// A run this window started and is watching (`WorkflowExecution`).
    struct LiveRun: Equatable {
        let id: String
        let name: String
        let step: String?
    }

    static let errorsShown = 3

    var running: [Item] = []
    /// Jobs queued and not started, counted (a waiting row stands for `total` jobs).
    var waitingCount = 0
    /// The reason most of the waiting jobs give.
    var waitingReason: String?
    /// The newest failures, at most `errorsShown`, each with its reason.
    var recentErrors: [Item] = []
    /// Why heavy work is held back now, or nil when it is not.
    var heldBack: String?
    /// This Mac's state, one line per reading the engine took; a reading it
    /// could not take (null) is left out rather than guessed.
    var macState: [String] = []

    init(jobs: [ActivityJob], paused: Bool, machine: Components.Schemas.MachineState? = nil, liveRuns: [LiveRun] = []) {
        var seen = Set<String>()
        for run in liveRuns where seen.insert(run.id).inserted {
            running.append(Item(id: run.id, name: run.name, detail: run.step))
        }
        var reasons: [String: Int] = [:]
        for job in jobs {
            switch job.state {
            case .running, .stalled:
                // A page under a run is that run's work, said once by the run.
                guard job.parentId == nil, seen.insert(job.id).inserted else { continue }
                running.append(Item(id: job.id, name: job.name,
                                    detail: job.showsProgress ? "\(job.current) of \(job.total)" : nil))
            case .waiting:
                let count = max(job.total, 1)
                waitingCount += count
                if let reason = job.reason, !reason.isEmpty { reasons[reason, default: 0] += count }
            case .failed:
                if recentErrors.count < Self.errorsShown {
                    recentErrors.append(Item(id: job.id, name: job.name, detail: job.reason))
                }
            case .paused, .completed, .other:
                continue
            }
        }
        waitingReason = reasons.max { lhs, rhs in
            lhs.value != rhs.value ? lhs.value < rhs.value : lhs.key > rhs.key
        }?.key
        heldBack = Self.heldBack(paused: paused, whyWait: machine?.whyWait, waitingReason: waitingReason)
        if let machine { macState = Self.lines(machine) }
    }

    private static func lines(_ machine: Components.Schemas.MachineState) -> [String] {
        var lines: [String] = []
        if let memory = machine.memoryPressure { lines.append("Memory pressure: \(memory.rawValue)") }
        if let heat = machine.thermalState { lines.append("Heat: \(heat.rawValue)") }
        lines.append(machine.onBattery == true ? "On battery" : "On power")
        lines.append(machine.inUse == true ? "In use" : "Not in use")
        return lines
    }

    /// A person's pause first; else the throttle's own reason now
    /// (`machine.why_wait`, `execution/throttle.py`: memory, heat, battery,
    /// the person at the Mac); else the reason a waiting job gives. A lane's
    /// wait is not one.
    private static func heldBack(paused: Bool, whyWait: String?, waitingReason: String?) -> String? {
        if paused { return "Background work is paused. Work you start still runs." }
        if let whyWait, !whyWait.isEmpty { return "Heavy work is held back: " + whyWait }
        guard let reason = waitingReason, reason.hasPrefix(throttlePrefix) else { return nil }
        return "Heavy work is held back: " + reason.dropFirst(throttlePrefix.count)
    }

    private static let throttlePrefix = "Waiting: "
}

/// The popover's summary, drawn: running now, waiting and why, the last
/// errors with their reasons, and what holds heavy work back.
struct ActivityPopoverSummaryView: View {
    let summary: ActivityPopoverSummary
    /// No import or engine task is showing above, so an empty summary says so.
    let nothingElseRunning: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(summary.running) { item in
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.name).font(.callout).lineLimit(1)
                        if let detail = item.detail {
                            Text(detail).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        }
                    }
                }
            }
            if summary.running.isEmpty && nothingElseRunning {
                Text("Nothing running.").font(.callout).foregroundStyle(.secondary)
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
            if !summary.macState.isEmpty {
                Text("This Mac").font(.caption).foregroundStyle(.secondary)
                ForEach(summary.macState, id: \.self) { line in
                    Text(line).font(.callout).foregroundStyle(.secondary)
                }
                .accessibilityIdentifier("activity.popover.macState")
            }
            if !summary.recentErrors.isEmpty {
                Text("Recent errors").font(.caption).foregroundStyle(.secondary)
                ForEach(summary.recentErrors) { item in
                    Label {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.name).font(.callout).lineLimit(1)
                            if let reason = item.detail, !reason.isEmpty {
                                Text(reason).font(.caption).lineLimit(2)
                            }
                        }
                    } icon: {
                        Image(systemName: "exclamationmark.triangle.fill")
                    }
                    .foregroundStyle(.red)
                }
            }
        }
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
                                  inUse: true, whyWait: "memory is tight")
        ),
        nothingElseRunning: true
    )
    .padding()
    .frame(width: 300)
}
