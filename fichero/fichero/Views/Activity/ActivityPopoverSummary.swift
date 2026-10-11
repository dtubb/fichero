import FicheroAPIClient
import SwiftUI

/// One stage of a recipe run in the Activity popover (#5666), with its own bar.
struct ActivityPopoverStage: Equatable, Identifiable {
    let id: String
    /// The stage's workflow by name ("Transcribe (Kraken)").
    let title: String
    /// "Running", "Done", "Waiting: the model lane", "Failed: …".
    let state: String
    /// Its pages done and in all, for its bar; 0 of 0 before it has any.
    let done: Int
    let total: Int
    let isRunning: Bool
    let isFailed: Bool
}

/// What the toolbar's Activity popover says (`activity.popover.summary`,
/// #5415): a summary, not a list. A recipe run in hand as one run with its
/// stages under it (#5666), what else is running now, how much is waiting
/// and the main reason, the recent errors with why (the run in hand's, else
/// the newest), worded without file paths, and whether heavy work is held back
/// and why, and this Mac's state (memory pressure, heat, battery, in use). Built from the one jobs read (`ActivityStore.backgroundJobs`
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

    /// A recipe run in hand (#5666): one run with its stages under it, never its stages again as jobs of their
    /// own. Worded by the Activity details (`ActivityDetails.stages`), from the run's tree in the store.
    struct Run: Equatable, Identifiable {
        let id: String
        let name: String
        /// What the run itself waits for while no stage runs ("Waiting for the model lane").
        let waiting: String?
        let stages: [ActivityPopoverStage]
    }

    static let errorsShown = 3

    /// The recipe runs in hand, each with its stages.
    var runs: [Run] = []
    var running: [Item] = []
    /// Jobs queued and not started, counted (a waiting row stands for `total` jobs).
    var waitingCount = 0
    /// The reason most of the waiting jobs give.
    var waitingReason: String?
    /// The recent failures, at most `errorsShown`, each with its reason in words: while a run is in hand, its
    /// own; else the newest the engine lists (#5666: older ones are the Activity window's).
    var recentErrors: [Item] = []
    /// How many failures are in that scope, for the badge; more than `recentErrors` holds when it is capped.
    var errorCount = 0
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
         runTrees: [String: ActivityJobNode] = [:], processCpuPercent: Double? = nil, cpuCount: Int = 0) {
        // A recipe run in hand, and everything under it: said once, by the run (#5666).
        let inHand = Self.runsInHand(jobs, runTrees: runTrees)
        runs = inHand.runs
        let inRun = inHand.ids
        var seen = inRun
        for run in liveRuns where seen.insert(run.id).inserted {
            running.append(Item(id: run.id, name: run.name, detail: run.step))
        }
        var reasons: [String: Int] = [:]
        // A run's own stages and steps are its, not jobs of their own; its failures are still counted.
        for job in jobs where job.state.isFailed || !inRun.contains(job.id) {
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
                // Only recent ones (#5666): while a run is in hand, its own failures; else every one listed.
                guard Self.isRecent(job, inRun: inRun) else { continue }
                errorCount += 1
                if recentErrors.count < Self.errorsShown {
                    recentErrors.append(Item(id: job.id, name: job.name, detail: job.reason.map(Self.worded)))
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

    /// The recipe runs in hand, with every id under them (the runs, their stages' runs, their steps and pages).
    private static func runsInHand(_ jobs: [ActivityJob], runTrees: [String: ActivityJobNode]) -> (runs: [Run], ids: Set<String>) {
        var runs: [Run] = []
        var ids = Set<String>()
        for job in jobs where isRunInHand(job) {
            let node = runTrees[job.id]
            runs.append(run(job, node: node))
            ids.insert(job.id)
            if let node {
                ids.formUnion(Self.ids(under: node))
                ids.formUnion(node.stages.compactMap(\.childId))
            }
        }
        return (runs, ids)
    }

    /// Whether a failure is the popover's (#5666): with no run in hand, every one listed; with one, only its own
    /// (the run, a stage's run, a step or a page under it). Older ones are the Activity window's.
    private static func isRecent(_ job: ActivityJob, inRun: Set<String>) -> Bool {
        inRun.isEmpty || [job.id, job.runId, job.parentId].contains { $0.map(inRun.contains) == true }
    }

    /// A recipe run that is going, waiting or paused, as the project's run strip follows it.
    private static func isRunInHand(_ job: ActivityJob) -> Bool {
        job.taskType == ActivityStore.recipeRunKind && job.parentId == nil && !job.id.hasPrefix("waiting:")
            && (job.state.isActive || job.state == .waiting)
    }

    /// The run with its stages, from its tree (none yet before the tree is read).
    private static func run(_ job: ActivityJob, node: ActivityJobNode?) -> Run {
        let words = ActivityDetails.stages(of: node)
        let stages = zip(node?.stages ?? [], words).map { stage, word in
            ActivityPopoverStage(
                id: word.id, title: word.title,
                state: word.waitingFor.map { "Waiting: \(worded($0))" } ?? worded(word.state),
                done: stage.account?.pagesDone ?? 0, total: stage.account?.pagesTotal ?? 0,
                isRunning: stage.state == "running", isFailed: word.isFailed
            )
        }
        let anyRunning = stages.contains(where: \.isRunning)
        return Run(id: job.id, name: job.name,
                   waiting: anyRunning ? nil : (node?.reason ?? job.reason).map(worded), stages: stages)
    }

    private static func ids(under node: ActivityJobNode) -> [String] {
        node.children.flatMap { [$0.id] + ids(under: $0) }
    }

    /// A reason in words, without file paths or file names (#5666): a path or an image's name becomes
    /// "a page", any other file's "a file", so an error reads as what happened, not where on disk.
    static func worded(_ text: String) -> String {
        let image = "jpe?g|png|tiff?|heic|gif|bmp|webp|jp2|pdf"
        var words = text
        let rules: [(String, String)] = [
            // A path to an image or a PDF: its folders may hold spaces ("EAP 1740"), its file's name does not.
            (#"(?:~|…|\.\.\.)?/(?:[^/\n:,;'"]+/)*[^/\s:,;'"]+\.(?:\#(image))\b"#, "a page"),
            // A path to any other file; then a path with no extension at all.
            (#"(?:~|…|\.\.\.)?/(?:[^/\n:,;'"]+/)*[^/\s:,;'"]+\.\w+\b"#, "a file"),
            (#"~?/[^\s:,;'"]+/[^\s:,;'"]+"#, "a file"),
            // A file's own name, with or without a leading ellipsis.
            (#"(?:…|\.\.\.)?[\w()\[\]~-]+(?:[.][\w()\[\]~-]+)*\.(?:\#(image))\b"#, "a page"),
            (#"(?:…|\.\.\.)?[\w()\[\]~-]+\.(?:xml|json|txt|csv|zip|alto|hocr|mlmodel|safetensors)\b"#, "a file")
        ]
        for (pattern, replacement) in rules {
            words = words.replacingOccurrences(of: pattern, with: replacement, options: [.regularExpression, .caseInsensitive])
        }
        for phrase in ["a page", "a file"] {
            words = words.replacingOccurrences(of: "'\(phrase)'", with: phrase)
                .replacingOccurrences(of: "\"\(phrase)\"", with: phrase)
                .replacingOccurrences(of: "‘\(phrase)’", with: phrase)
        }
        return words.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespaces)
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
            ForEach(summary.runs) { run in
                ActivityPopoverRunView(run: run)
            }
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
            if summary.running.isEmpty && summary.runs.isEmpty && nothingElseRunning {
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
            if summary.errorCount > 0 {
                // A count that opens the detail (#5666): errors never crowd out the work in hand.
                ActivityPopoverErrorsBadge(summary: summary)
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
