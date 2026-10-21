import Foundation

/// One row of the Activity window's table (#2546 / B2, rebuilt for #5415):
/// a run, a step, a page, or a job of its own (an embedding queue, a waiting
/// kind of work).
///
/// The tree is the engine's (`GET /api/activity/jobs/{id}`, #5353): a run's
/// steps and their pages, with time, cost and errors rolled up. A run the
/// engine has no tree for still has its row, from the runs table alone.
///
/// Every level shares this one row type so a `Table` renders them with one
/// set of columns. Display values are precomputed here so the column closures
/// stay tiny: hierarchical `Table` bodies type-check slowly.
struct ActivityMonitorRow: Identifiable, Equatable {
    enum Kind { case run, step, page, job }

    /// What a row's Pause, Resume, Stop and Retry buttons offer.
    enum Control: String, Identifiable {
        /// `carryOn` is the engine's offer on a job set aside after its interruptions (#5615): it reads Resume and
        /// is done by the job's retry, which carries it on from where it was.
        case pause, resume, stop, retry, carryOn
        var id: String { rawValue }
        var label: String {
            switch self {
            case .pause: "Pause"
            case .resume, .carryOn: "Resume"
            case .stop: "Stop"
            case .retry: "Retry"
            }
        }
        var systemImage: String {
            switch self {
            case .pause: "pause.fill"
            case .resume, .carryOn: "play.fill"
            case .stop: "stop.fill"
            case .retry: "arrow.counterclockwise"
            }
        }
        /// Done by the job's retry (`POST /api/activity/jobs/{id}/retry`).
        var isRetry: Bool { self == .retry || self == .carryOn }
    }

    /// Unique across levels and projects.
    let id: String
    let kind: Kind
    let libraryId: UUID?
    /// The owning run's row id (`ActivityRun.id`): what Delete and the detail
    /// window act on from any row of its tree.
    let runRowID: String?
    /// The owning run's thread id: the key of its tree in `ActivityStore`.
    let runThreadId: String?
    /// The job Pause and Stop act on (`/api/activity/jobs/{id}/…`); `nil` for
    /// a row with no job behind it, which shows no controls.
    let jobId: String?
    let name: String
    /// The project, shown before a run's name when rows are not grouped.
    let projectName: String?
    let phase: Phase
    /// Why it failed, or what it is waiting for, in the engine's words.
    let reason: String?
    /// What a running row is working on now.
    let workingOn: String?
    let done: Int
    let total: Int
    let started: Date?
    /// How long it took, start to finish (or until the last read, while it runs).
    let seconds: Double?
    let costUsd: Double?
    let tokens: Int
    let errors: Int
    let model: String?
    /// Live from this window's own executions: its time ticks as a timer.
    let isLive: Bool
    /// `nil` = a leaf (no disclosure triangle).
    var children: [ActivityMonitorRow]?
    /// A run's account (#5555): what its row says beyond the counts. `nil`
    /// on steps, pages, other jobs and runs the engine has no account for.
    var account: ActivityRunAccount?
    /// The engine's kind of work ("read-a-page", "train-a-model", …), for the
    /// row's kind icon (#5560); `nil` when the row has no job behind it.
    var engineKind: String?
    /// A job of its own's id (an embedding queue): what its details read
    /// (#5561); the same as its `jobId`, which its Pause and Stop act on (#5621).
    var ownJobId: String?
    /// What the engine offers on the row (#5615): "Resume" on a job set aside after its interruptions.
    var offer: String?
    /// Where a waiting job of its own stands in the engine's list, which is the order the lane will pick them (#5839).
    var queuePosition: Int?
    /// The engine's own name for a state this app does not know, said as "unknown state <name>" (#5957).
    var unknownState: String?
    /// "Stopping", "Pausing", "Resuming" or "Retrying" while the engine is part-way through that: a run just Stopped
    /// does not read "Running" (## 697, #5957). The phase stays running (it is still live, and sorts so).
    var transientState: String?
    /// When it ended: the engine's finished time if it sent one, else the failure time, else start plus duration; nil
    /// when none is known (DONE TODAY then lists it rather than lose it; `activity.window.done-today`).
    var ended: Date?

    // MARK: - Waiting looks like waiting (#5839)

    /// Not started yet: the engine lists the row as waiting (a queued job, or a running one whose wait it has named,
    /// like a try whose page waits for the lane). It shows no spinner, no progress and no ticking timer, only a grey
    /// "Waiting: <reason>". Never inferred from the reason's words or a run's counts: a run with one page running
    /// and another waiting is running.
    var looksWaiting: Bool { phase == .waiting }

    // MARK: - Icons (#5560)

    /// What kind of row it is, as an SF Symbol: a run, a step, a page, a model
    /// load, training, or other work of its own.
    var kindSymbol: String {
        let work = (engineKind ?? "").lowercased()
        if work.contains("train") { return "graduationcap" }
        if work.contains("download") || work.contains("load-model") || work.contains("install") {
            return "arrow.down.circle"
        }
        switch kind {
        case .run: return "flowchart"
        case .step: return "list.bullet.indent"
        case .page: return "doc.text"
        case .job: return "gearshape"
        }
    }

    /// The kind in words, for VoiceOver beside the icon.
    var kindWord: String {
        switch kindSymbol {
        case "graduationcap": "Training"
        case "arrow.down.circle": "Model load"
        case "flowchart": "Run"
        case "list.bullet.indent": "Step"
        case "doc.text": "Page"
        default: "Job"
        }
    }

    /// The job the details view reads for this row (#5561): its own job, a
    /// run's thread id before its tree is loaded, or a job of its own's id.
    var detailsJobId: String? { jobId ?? runThreadId ?? ownJobId }

    /// Whether ⓘ (and double-click) can open this row's log and details:
    /// every row with a job behind it, a job of its own too (#5561).
    var opensDetails: Bool { detailsJobId != nil }

    /// The details' selection for this row: its job and its project.
    var selection: ActivitySelection? {
        detailsJobId.map { ActivitySelection(jobId: $0, libraryId: libraryId) }
    }

    // MARK: - Columns

    /// "Failed: the provider refused this letter", "Waiting: memory is tight",
    /// "Running: Entities". The reason is the point of a failed row.
    var stateText: String {
        Self.stateText(phase: phase, reason: reason, workingOn: workingOn, account: account)
    }

    /// The State column's words, shared with the details view so the two never
    /// word a row differently (`activity.details.state-says-why`, #5561).
    static func stateText(phase: Phase, reason: String?, workingOn: String?, account: ActivityRunAccount?) -> String {
        // An interrupted run says so, and when ("Interrupted: the engine stopped at 14:05, …").
        if let account, account.interrupted, let why = account.reason ?? reason {
            return why
        }
        if phase == .running, let transientState { return transientState }
        // A running run whose page waits (for memory, #5537) says what for.
        if phase == .running, let waiting = account?.waitingReason, !waiting.isEmpty {
            return waiting.hasPrefix("Waiting") ? waiting : "Waiting: \(waiting)"
        }
        if let reason, !reason.isEmpty, phase == .failed || phase == .waiting || phase == .paused {
            if reason.lowercased().hasPrefix(phase.word.lowercased()) || reason.hasPrefix("Paused") {
                return reason
            }
            return "\(phase.word): \(reason)"
        }
        if phase == .running, let workingOn, !workingOn.isEmpty {
            return "Running: \(workingOn)"
        }
        if phase == .done, let partial = partialWords(reason) { return partial }
        if phase == .unknown { return "unknown state \(unknownState ?? "")".trimmingCharacters(in: .whitespaces) }
        if let reason, !reason.isEmpty, phase == .partial || phase == .interrupted || phase == .notRun {
            return reason.lowercased().hasPrefix(phase.word.lowercased()) ? reason : "\(phase.word): \(reason)"
        }
        return phase.word
    }

    /// A finished run that lost pages keeps the state `done` and says "Partial: 8 of 10 pages read (2 stopped)" in its reason
    /// (`activity.run.partial-said-on-a-done-row`, #5937): shown instead of plain Done/Completed. Nil for any other reason.
    static func partialWords(_ reason: String?) -> String? {
        guard let reason, reason.hasPrefix("Partial") else { return nil }
        return reason
    }

    /// Seconds left at the pace so far, while it runs and some are done: the
    /// engine's estimate when the run's account has one.
    var remainingSeconds: Double? {
        guard phase == .running else { return nil }
        if let estimate = account?.estimateSecondsLeft { return estimate }
        guard let seconds, done > 0, total > done else { return nil }
        return seconds / Double(done) * Double(total - done)
    }

    /// The run's failed pages with why, one a line, then its peak memory:
    /// what the State cell's help shows (#5555).
    var accountDetail: String? {
        guard let account else { return nil }
        var lines = account.failures.map { failure in
            "\(failure.title): \(failure.reason)" + (failure.retried ? " (read twice)" : "")
        }
        if account.pagesFailed > account.failures.count {
            lines.append("and \(account.pagesFailed - account.failures.count) more")
        }
        if let peak = peakMemoryText { lines.append(peak) }
        return lines.isEmpty ? nil : lines.joined(separator: "\n")
    }

    /// "Peak memory: engine 2.0 GB, model server 3.5 GB" (#5537), when measured.
    var peakMemoryText: String? {
        guard let account else { return nil }
        let parts = [
            account.enginePeakMemoryBytes.map { "engine \(Self.gigabytes($0))" },
            account.modelServerPeakMemoryBytes.map { "model server \(Self.gigabytes($0))" }
        ].compactMap { $0 }
        return parts.isEmpty ? nil : "Peak memory: " + parts.joined(separator: ", ")
    }

    /// "Read the 3 pages that failed": the run's one action at its end, or nil.
    var readAgainLabel: String? {
        guard kind == .run, !phase.isLive else { return nil }
        return account?.offerLabel
    }

    static func gigabytes(_ bytes: Int) -> String {
        let value = Double(bytes) / 1_073_741_824
        return value.formatted(.number.precision(.fractionLength(1)).locale(Locale(identifier: "en_US_POSIX"))) + " GB"
    }

    /// The name a row shows: with several projects' work in the window the project leads it, with one no project is named
    /// (`activity.window.project-prefix`, #5960).
    nonisolated func displayName(showsProject: Bool) -> String {
        if showsProject, let projectName, !projectName.isEmpty { return "\(projectName) · \(name)" }
        return name
    }

    /// "12 of 40", plus "about 3 min left" while it runs.
    var progressText: String {
        guard total > 0, !looksWaiting else { return "" }
        let counts = "\(done) of \(total)"
        guard let remaining = remainingSeconds else { return counts }
        return "\(counts), \(Self.duration(remaining)) left"
    }

    /// "$0.0023"; "Not priced" when a call under it has no price; empty when
    /// nothing under it called a model. Never zero for unknown.
    var costText: String {
        if let costUsd {
            // Dollars, as the price list states them, in any locale.
            return "$" + costUsd.formatted(.number.precision(.significantDigits(1...3)).locale(Locale(identifier: "en_US_POSIX")))
        }
        return tokens > 0 ? "Not priced" : ""
    }

    var secondsText: String { looksWaiting ? "" : (seconds.map(Self.duration) ?? "") }

    var errorsText: String { errors > 0 ? "\(errors)" : "" }

    /// What Pause and Stop offer on this row: nothing on a finished row, or a
    /// row with no job behind it.
    var controls: [Control] {
        switch phase {
        case .running, .waiting: return jobId == nil ? [] : [.pause, .stop]
        case .paused: return jobId == nil ? [] : [.resume, .stop]
        // #5356: a failed or stopped row, a job of its own too, offers Retry; one the engine set aside after its
        // interruptions offers Resume instead, as the engine says (#5615).
        case .failed, .cancelled, .interrupted:
            guard retryJobId != nil else { return [] }
            return offer == "Resume" ? [.carryOn] : [.retry]
        case .done, .partial, .notRun, .unknown: return []
        }
    }

    /// The job Retry acts on (`POST /api/activity/jobs/{id}/retry`): the row's
    /// own job, or a job of its own's id from the jobs read.
    var retryJobId: String? { jobId ?? ownJobId }

    // MARK: - Sort keys (non-optional, so a column can sort on them)

    /// Live rows first: the default order is what is happening now, then the newest.
    var liveKey: Int { phase.isLive ? 0 : 1 }
    var phaseKey: Int { phase.rawValue }
    /// Running work before waiting work, and waiting work in the order the lane picks it (#5839).
    var waitingKey: Int { looksWaiting ? 1 : 0 }
    var queueKey: Int { queuePosition ?? Int.max }
    var waitingStartedKey: Date { looksWaiting ? (started ?? .distantFuture) : .distantPast }
    var startedKey: Date { started ?? .distantPast }
    var secondsKey: Double { seconds ?? -1 }
    var costKey: Double { costUsd ?? -1 }
    var progressKey: Double { total > 0 ? Double(done) / Double(total) : -1 }
    var modelKey: String { model ?? "" }

    static let defaultSort: [KeyPathComparator<ActivityMonitorRow>] = [
        KeyPathComparator(\.liveKey),
        KeyPathComparator(\.waitingKey),
        KeyPathComparator(\.queueKey),
        KeyPathComparator(\.waitingStartedKey),
        KeyPathComparator(\.startedKey, order: .reverse)
    ]

    /// Rows in `comparators`' order, each level's children too.
    static func sorted(
        _ rows: [ActivityMonitorRow],
        using comparators: [KeyPathComparator<ActivityMonitorRow>]
    ) -> [ActivityMonitorRow] {
        rows.sorted(using: comparators).map { row in
            var row = row
            row.children = row.children.map { sorted($0, using: comparators) }
            return row
        }
    }

    static func duration(_ seconds: Double) -> String {
        Duration.seconds(seconds.rounded()).formatted(
            .units(allowed: [.hours, .minutes, .seconds], width: .abbreviated, maximumUnitCount: 2)
        )
    }
}
