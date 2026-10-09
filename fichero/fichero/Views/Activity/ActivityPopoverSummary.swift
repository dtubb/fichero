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
    /// This Mac's state as a row of symbols (`activity.popover.mac-state-row`,
    /// #5635): one per reading the engine took, then the app's CPU; a reading
    /// it could not take (null) is left out rather than guessed.
    var macReadings: [MacReading] = []

    /// One reading of this Mac's state: a symbol, a short value, the full
    /// reading in words (help and accessibility), tinted only when a problem.
    struct MacReading: Equatable, Identifiable {
        let id: String
        let symbol: String
        let value: String
        let help: String
        var isProblem = false
    }

    init(jobs: [ActivityJob], paused: Bool, machine: Components.Schemas.MachineState? = nil, liveRuns: [LiveRun] = [],
         processCpuPercent: Double? = nil, cpuCount: Int = 0) {
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
        heldBack = Self.heldBack(paused: paused, whyWait: waitingCount > 0 ? machine?.whyWait : nil,
                                 waitingReason: waitingReason)
        macReadings = (machine.map(Self.readings) ?? [])
            + (processCpuPercent.map { [Self.cpuReading($0, cpuCount: cpuCount)] } ?? [])
    }

    private static func readings(_ machine: Components.Schemas.MachineState) -> [MacReading] {
        var readings: [MacReading] = []
        if let memory = machine.memoryPressure {
            let value: String
            switch memory {
            case .normal: value = "OK"
            case .warn: value = "High"
            case .critical: value = "Critical"
            }
            readings.append(MacReading(
                id: "memory", symbol: "memorychip", value: value,
                help: "Memory pressure: " + (memory == .normal ? "normal" : value.lowercased()),
                isProblem: memory != .normal))
        }
        if let heat = machine.thermalState {
            let value: String
            switch heat {
            case .nominal: value = "OK"
            case .fair: value = "Warm"
            case .serious: value = "Hot"
            case .critical: value = "Critical"
            }
            readings.append(MacReading(
                id: "heat", symbol: "thermometer.medium", value: value,
                help: "Heat: " + (heat == .nominal ? "normal" : value.lowercased()),
                isProblem: heat == .serious || heat == .critical))
        }
        readings.append(machine.onBattery == true
            ? MacReading(id: "power", symbol: "battery.50percent", value: "Battery", help: "On battery")
            : MacReading(id: "power", symbol: "powerplug", value: "Power", help: "On power"))
        readings.append(machine.inUse == true
            ? MacReading(id: "person", symbol: "person.fill", value: "In use", help: "You're using the Mac")
            : MacReading(id: "person", symbol: "person", value: "Away", help: "Nobody is using the Mac"))
        return readings
    }

    /// The app's processor use, where 100% is one core busy; the help says of how much.
    private static func cpuReading(_ percent: Double, cpuCount: Int) -> MacReading {
        let value = "\(Int(percent.rounded()))%"
        let whole = cpuCount > 0 ? " of \(cpuCount * 100)% (\(cpuCount) cores)" : ""
        return MacReading(id: "cpu", symbol: "cpu", value: value, help: "Fichero's processor use: " + value + whole)
    }

    /// A person's pause first; else, only while some work waits (nothing held back is not "held back",
    /// maintainer 2026-10-09), the throttle's own reason now
    /// (`machine.why_wait`, `execution/throttle.py`: memory, heat, battery,
    /// the person at the Mac); else the reason a waiting job gives. A lane's
    /// wait is not one.
    private static func heldBack(paused: Bool, whyWait: String?, waitingReason: String?) -> String? {
        if paused { return "Background work is paused. Work you start still runs." }
        // The throttle's reason may arrive with its own "Waiting: " (as a job's does): said once.
        if let whyWait, !whyWait.isEmpty {
            return "Heavy work is held back: "
                + (whyWait.hasPrefix(throttlePrefix) ? String(whyWait.dropFirst(throttlePrefix.count)) : whyWait)
        }
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
            if !summary.macReadings.isEmpty {
                ActivityMacStateRow(readings: summary.macReadings)
            }
            if !summary.recentErrors.isEmpty {
                // One line each, the full name and reason in its help (#5635).
                VStack(alignment: .leading, spacing: 3) {
                    ForEach(summary.recentErrors) { item in
                        Label(Self.oneLine(item), systemImage: "exclamationmark.triangle.fill")
                            .font(.caption)
                            .lineLimit(1)
                            .truncationMode(.tail)
                            .foregroundStyle(.red)
                            .help(Self.words(item).joined(separator: "\n"))
                    }
                }
                .accessibilityIdentifier("activity.popover.errors")
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

/// This Mac's state as one compact row of symbols with short values
/// (`activity.popover.mac-state-row`, #5635): each says its full reading in
/// its help and to accessibility; only a problem is tinted.
struct ActivityMacStateRow: View {
    let readings: [ActivityPopoverSummary.MacReading]

    var body: some View {
        HStack(spacing: 12) {
            ForEach(readings) { reading in
                HStack(spacing: 3) {
                    Image(systemName: reading.symbol)
                    Text(reading.value).monospacedDigit()
                }
                .font(.caption)
                .foregroundStyle(reading.isProblem ? AnyShapeStyle(.orange) : AnyShapeStyle(.secondary))
                .help(reading.help)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(reading.help)
                .accessibilityIdentifier("activity.popover.macState.\(reading.id)")
            }
        }
        .fixedSize()
        .accessibilityElement(children: .contain)
        .accessibilityLabel("This Mac")
        .accessibilityIdentifier("activity.popover.macState")
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
        ),
        nothingElseRunning: true
    )
    .padding()
    .frame(width: 300)
}

#Preview("This Mac: all well, then hot with memory tight") {
    VStack(alignment: .leading, spacing: 12) {
        ActivityMacStateRow(readings: ActivityPopoverSummary(
            jobs: [], paused: false,
            machine: Components.Schemas.MachineState(memoryPressure: .normal, thermalState: .nominal, onBattery: false,
                                                     inUse: false, whyWait: nil),
            processCpuPercent: 2, cpuCount: 8
        ).macReadings)
        ActivityMacStateRow(readings: ActivityPopoverSummary(
            jobs: [], paused: false,
            machine: Components.Schemas.MachineState(memoryPressure: .critical, thermalState: .serious, onBattery: true,
                                                     inUse: true, whyWait: "the Mac is hot"),
            processCpuPercent: 412, cpuCount: 8
        ).macReadings)
    }
    .padding()
}
