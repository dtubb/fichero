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
        /// A running item's step or counts; a failed item's cause, its first sentence (the engine's words).
        let detail: String?
        /// A failed item's whole reason, as the engine wrote it, for the row's tooltip.
        var fullText: String?
        /// A running item's pages done and in all, for its bar (#5666); 0 of 0 when it has none.
        var done = 0
        var total = 0
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

    /// What is working right now, from the engine's one summary (`activity.popover.same-summary`, #5852): "Recipe ›
    /// Stage › Workflow" and "7 of 20 pages · 2 of 8 folders", the same words the window's live block has.
    struct Block: Equatable, Identifiable {
        let id: String
        let title: String
        let counts: String
        /// What a waiting block waits for; nil while it works.
        let waiting: String?
        /// The model by its own name and where it runs, the engine's words as sent ("Kraken · on this Mac"); nil with neither.
        var subtitle: String?
    }

    /// One kind of background work and its total, from the same summary; a wait looks waiting and says why.
    struct BackgroundRow: Equatable, Identifiable {
        let id: String
        let text: String
        let waiting: String?
    }

    /// One of the first UP NEXT items (`activity.popover.now-plus-next`): its name, and in grey what it waits for.
    struct UpNextLine: Equatable, Identifiable {
        let id: String
        let name: String
        let waiting: String
        /// The run a stage line belongs to (and its project when the list is grouped), so two runs' "Describe" differ.
        var run: String?

        /// "Describe · Mosquera box" (the stage, then its run).
        var title: String { run.map { "\(name) · \($0)" } ?? name }
    }

    static let errorsShown = 3
    static let upNextShown = 3

    /// The live blocks the engine's summary names, first in the popover.
    var blocks: [Block] = []
    /// One line per background kind with its total.
    var background: [BackgroundRow] = []
    /// The first three of the engine's `up_next`, in the order the lanes will take them.
    var upNext: [UpNextLine] = []

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
         runTrees: [String: ActivityJobNode] = [:], processCpuPercent: Double? = nil, cpuCount: Int = 0,
         errorWindow: ActivityErrorWindow? = nil, activity: Components.Schemas.ActivitySummary? = nil) {
        blocks = (activity?.live ?? []).map(Self.block)
        background = (activity?.background ?? []).map(Self.backgroundLine)
        let runNames = Dictionary(jobs.map { ($0.id, $0.name) }, uniquingKeysWith: { first, _ in first })
        upNext = (activity?.upNext ?? []).prefix(Self.upNextShown).map { Self.upNextLine($0, runName: { runNames[$0] }) }
        // A recipe run in hand, and everything under it: said once, by the run (#5666).
        let inHand = Self.runsInHand(jobs, runTrees: runTrees)
        runs = inHand.runs
        let inRun = inHand.ids
        let reasons = tally(jobs: jobs, inRun: inRun, liveRuns: liveRuns, activity: activity, errorWindow: errorWindow)
        waitingReason = reasons.max { lhs, rhs in
            lhs.value != rhs.value ? lhs.value < rhs.value : lhs.key > rhs.key
        }?.key
        heldBack = Self.heldBack(paused: paused, whyWait: waitingCount > 0 ? machine?.whyWait : nil,
                                 waitingReason: waitingReason)
        macReadings = (machine.map(Self.readings) ?? [])
            + (processCpuPercent.map { [Self.cpuReading($0, cpuCount: cpuCount)] } ?? [])
    }

    /// A failed job counts toward the badge and, while few, is listed with its cause.
    private mutating func noteFailure(_ job: ActivityJob, inRun: Set<String>, errorWindow: ActivityErrorWindow?) {
        // Only recent ones (#5666): while a run is in hand, its own; and only those from the last hour or
        // since the popover was last opened, whichever is shorter (`ActivityErrorWindow`).
        guard Self.isRecent(job, inRun: inRun), errorWindow?.isRecent(job.id) ?? true else { return }
        errorCount += 1
        if recentErrors.count < Self.errorsShown {
            // The engine's words (its failure is one line per cause, 1bef3cd4d): the first sentence shown,
            // the whole in the tooltip.
            recentErrors.append(Item(id: job.id, name: job.name, detail: job.reason.map(Self.firstSentence),
                                     fullText: job.reason))
        }
    }

    /// Sorts the jobs into running, waiting and failed for the popover; returns the waiting reasons with their page counts.
    private mutating func tally(jobs: [ActivityJob], inRun: Set<String>, liveRuns: [LiveRun],
                                activity: Components.Schemas.ActivitySummary?, errorWindow: ActivityErrorWindow?) -> [String: Int] {
        var seen = inRun
        for run in liveRuns where seen.insert(run.id).inserted {
            running.append(Item(id: run.id, name: run.name, detail: run.step))
        }
        var reasons: [String: Int] = [:]
        // A kind of background work the engine's summary has a line for is said once, by that line.
        let backgroundKinds = Set((activity?.background ?? []).map(\.kind))
        // A run's own stages and steps are its, not jobs of their own; its failures are still counted.
        for job in jobs where job.state.isFailed || !inRun.contains(job.id) {
            if backgroundKinds.contains(job.taskType), job.state == .running || job.state == .stalled || job.state == .waiting {
                continue
            }
            switch job.state {
            case .running, .stalled:
                // A page under a run is that run's work, said once by the run.
                guard job.parentId == nil, seen.insert(job.id).inserted else { continue }
                running.append(Item(id: job.id, name: job.name,
                                    detail: job.showsProgress ? "\(job.current) of \(job.total)" : nil,
                                    done: job.current, total: job.total))
            case .waiting:
                let count = max(job.total, 1)
                waitingCount += count
                if let reason = job.reason, !reason.isEmpty { reasons[reason, default: 0] += count }
            case .failed:
                noteFailure(job, inRun: inRun, errorWindow: errorWindow)
            case .paused, .completed, .other:
                continue
            }
        }
        return reasons
    }

    static func block(_ live: Components.Schemas.LiveBlock) -> Block {
        // The counts have engine defaults (0), so the generated client makes them optional.
        let total = live.total ?? 0, done = live.done ?? 0, failedCount = live.failed ?? 0
        let pages = total > 0 ? "\(done) of \(total) \(total == 1 ? "page" : "pages")" : "no pages yet"
        let folders = live.foldersTotal.map { "\(live.foldersDone ?? 0) of \($0) \($0 == 1 ? "folder" : "folders")" }
        let failed = failedCount > 0 ? "\(failedCount) failed" : nil
        return Block(
            id: live.id,
            title: [live.recipe, live.stage, live.workflow].compactMap { $0 }.joined(separator: " › "),
            counts: [pages, folders, failed].compactMap { $0 }.joined(separator: " · "),
            waiting: live.state == "waiting" ? live.reason.map(worded) : nil,
            subtitle: subtitle(model: live.model, place: live._where)
        )
    }

    static func backgroundLine(_ line: Components.Schemas.BackgroundLine) -> BackgroundRow {
        BackgroundRow(
            id: line.kind,
            text: (line.total ?? 0) > 0 ? "\(line.name) · \(line.done ?? 0) of \(line.total ?? 0)" : line.name,
            waiting: line.state == "waiting" ? (line.reason.map(worded) ?? "Waiting") : nil
        )
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
                // By Set Up's stage ("Read"), as the run's details read (#5670); a step no stage carries, its own.
                id: word.id, title: stage.steps.first.flatMap(SetupStages.stage(of:))?.title ?? word.title,
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

    /// A cause's first sentence: up to its first full stop followed by a space, or its first line (the engine's own
    /// words; nothing is rewritten).
    nonisolated static func firstSentence(_ text: String) -> String {
        let line = text.split(separator: "\n", maxSplits: 1).first.map(String.init) ?? text
        if let stop = line.range(of: ". ") { return String(line[..<stop.lowerBound]) + "." }
        return line.trimmingCharacters(in: .whitespaces)
    }

    /// A reason in words, without file paths or file names (#5666): a path or an image's name becomes
    /// "a page", any other file's "a file", so an error reads as what happened, not where on disk.
    nonisolated static func worded(_ text: String) -> String {
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
