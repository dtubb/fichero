import FicheroAPIClient
import SwiftUI

// The project window's own account of its recipe run (#5576, #5577;
// `source.onboard.auto.lands-on-the-run`, `source.onboard.auto.results-summary`):
// a compact strip along the bottom of the content column while a recipe run
// goes, and when it ends, what it made in one line. Worded from the recipe run's
// node of the job tree in the project's `ActivityStore` (`projectRunId`,
// `runTrees`), the record the Activity details read, through the same wording
// (`ActivityDetails.stages`, `ActivityDetails.summary`): nothing is fetched,
// polled or counted here.

/// What the strip says, in words.
struct ProjectRunStrip: Equatable {
    let jobId: String
    /// True while the run goes; false once it has ended.
    let isLive: Bool
    /// "Transcribe (Kraken) · stage 1 of 3", "Recipe run waiting", "Recipe run finished".
    let title: String
    /// Live: "1 done · 0 failed · 1 left · 2m left · Waiting: memory is tight".
    /// Ended: "Read 2 of 2 pages · Names: 1 People · 1 Places · 1 date · 1 statement".
    let detail: String
    /// An ended run's stages whose pages failed, each with its Read Again.
    let failed: [ActivityDetails.Summary.Failed]
    /// What an ended run missed and its Run Again (#6170), as the engine sends it.
    var missed: ActivityDetails.Summary.MissedOffer?

    /// The strip for the store's project run, or nil when there is none.
    @MainActor
    init?(store: ActivityStore) {
        guard let jobId = store.projectRunId else { return nil }
        self.init(jobId: jobId, node: store.runTrees[jobId],
                  job: store.backgroundJobs.first { $0.id == jobId },
                  folders: store.recipeRunFolders[jobId], pagesAtOnce: store.recipeRunPagesAtOnce[jobId])
    }

    /// Preview seam: the words given.
    init(jobId: String, isLive: Bool, title: String, detail: String, failed: [ActivityDetails.Summary.Failed] = []) {
        self.jobId = jobId
        self.isLive = isLive
        self.title = title
        self.detail = detail
        self.failed = failed
    }

    /// The strip from the run's node, its row on the jobs poll and its folders done of its folders
    /// (`activity.run.progress-per-folder`): pure, so a test can build it.
    init(jobId: String, node: ActivityJobNode?, job: ActivityJob?, folders: RecipeRunFolders? = nil,
         pagesAtOnce: RecipeRunPagesAtOnce? = nil) {
        self.jobId = jobId
        let state = Self.effectiveState(nodeState: node?.state, jobState: job?.state)
        let ended = ["done", "failed", "cancelled"].contains(state)
        isLive = !ended
        if ended {
            let summary = ActivityDetails.summary(of: node)
            switch state {
            case "done": title = "Recipe run finished"
            case "cancelled": title = "Recipe run stopped"
            default: title = "Recipe run failed"
            }
            // No account of what it made: say so, never a bare "finished" (the tree read, which carries the summary, can fail
            // while the jobs list already says the run ended).
            detail = summary?.lines.joined(separator: " · ")
                ?? [node?.reason, job?.reason].compactMap { $0 }.first { !$0.isEmpty }
                ?? "What it made could not be read just now. Show Details has the log."
            failed = summary?.failed ?? []
            missed = summary?.missed
            return
        }
        failed = []
        if state == "stalled" {
            title = ["Recipe run stalled", folders?.words].compactMap { $0 }.joined(separator: " · ")
            detail = [job?.reason, node?.reason].compactMap { $0 }.first { !$0.isEmpty }
                ?? "Nothing has moved for a while. Show Details has the log."
            return
        }
        let words = Self.liveWords(state: state, node: node, job: job)
        // How far the run is in folders, after its stage, for a run over more than one (#5540).
        title = [words.title, folders?.words].compactMap { $0 }.joined(separator: " · ")
        // Then how many pages it reads at once and why, as the engine sends them (#6217).
        detail = [words.detail, pagesAtOnce?.words].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
    }

    /// The state the strip goes by. The run's tree is the record, but a failed tree read keeps the last tree (`ActivityStore`
    /// `fetchRunTree`), so a run that has ended can still look running there while the jobs list, polled, already says it ended
    /// or stalled: an end or a stall in the list wins over a tree that has not caught up. Pure, tested without a store.
    nonisolated static func effectiveState(nodeState: String?, jobState: ActivityJob.State?) -> String {
        if let nodeState, ["done", "failed", "cancelled"].contains(nodeState) { return nodeState }
        switch jobState {
        case .completed: return "done"
        case .failed: return "failed"
        case .stalled: return "stalled"
        default: return nodeState ?? (jobState == .running ? "running" : "waiting")
        }
    }

    /// A live run's title and line: its running stage by name, that stage's
    /// run account (pages done, failed and left, time left, what its pages
    /// wait for); before a stage runs, what the run itself waits for.
    private static func liveWords(state: String, node: ActivityJobNode?, job: ActivityJob?) -> (title: String, detail: String) {
        let stages = ActivityDetails.stages(of: node)
        if let running = node?.stages.firstIndex(where: { $0.state == "running" }), running < stages.count {
            let stage = stages[running]
            var parts: [String] = []
            if let counts = stage.counts { parts.append(counts) }
            if let timeLeft = stage.timeLeft { parts.append("\(timeLeft) left") }
            // Only the stage's own wait: while a stage runs, the run's reason is its progress ("Running the
            // recipe: 3 of 800 folders done"), shown as the folders count, never as a wait.
            if let waiting = stage.waitingFor { parts.append("Waiting: \(waiting)") }
            return ("\(stage.title) · stage \(running + 1) of \(stages.count)", parts.joined(separator: " · "))
        }
        // Not in a stage yet: the run's reason says what it waits for (another run, memory).
        let reason = node?.reason ?? job?.reason ?? ""
        switch state {
        case "paused": return ("Recipe run paused", reason)
        case "running": return ("Recipe run starting", reason)
        default: return ("Recipe run waiting", reason)
        }
    }
}

/// A recipe run's folders done of its folders in all (`activity.run.progress-per-folder`, #5540), as the
/// run's status carries them (`folders_done`, `folders_total`). The engine counts; the app only words it.
struct RecipeRunFolders: Equatable {
    let done: Int
    let total: Int

    /// nil before the run has worked out its folders.
    init?(_ status: Components.Schemas.RecipeRunStatus) {
        guard let total = status.foldersTotal else { return nil }
        self.init(done: status.foldersDone ?? 0, total: total)
    }

    init(done: Int, total: Int) {
        self.done = done
        self.total = total
    }

    /// "3 of 800 folders"; nil for a run over one folder or none (an import's one batch, a folder with none inside),
    /// where it would say nothing the stage does not.
    var words: String? {
        total > 1 ? "\(done) of \(total) folders" : nil
    }
}

/// How many pages a recipe run reads at once now, and which hold makes it one (`recipes-run.memory.gate-shown`, #6217),
/// as the run's status carries them (`pages_at_once`, `pages_at_once_reason`). The engine decides; the app only words it.
struct RecipeRunPagesAtOnce: Equatable {
    let count: Int
    let reason: String?

    /// nil when the status says nothing: the run is not going.
    init?(_ status: Components.Schemas.RecipeRunStatus) {
        guard let count = status.pagesAtOnce else { return nil }
        self.init(count: count, reason: status.pagesAtOnceReason)
    }

    init(count: Int, reason: String?) {
        self.count = count
        self.reason = reason
    }

    /// "reading 2 pages at once"; "one page at a time: the Mac is paging".
    var words: String {
        count > 1 ? "reading \(count) pages at once"
            : ["one page at a time", reason].compactMap { $0 }.joined(separator: ": ")
    }
}

/// The strip itself: one row along the bottom of the content column, beneath
/// the library's own bottom bar (`ContentView.detailColumn`'s bottom inset).
/// Shown only while the project has a recipe run to show.
struct ProjectRunStripView: View {
    let libraryId: UUID
    @Environment(ActivityStore.self) private var store
    @Environment(\.openWindow) private var openWindow
    @State private var failure: String?

    var body: some View {
        if let strip = ProjectRunStrip(store: store) {
            ProjectRunStripRow(
                strip: strip,
                failure: failure,
                readAgain: { threadId, offer in
                    .stage(threadId: threadId, offer: offer, store: store, report: { failure = $0 })
                },
                runAgain: { folderId in
                    Task { failure = await LibraryManager.shared.runAgainOnMissed(for: libraryId, folderId: folderId) }
                },
                onShowDetails: { showDetails(strip.jobId) },
                onClose: { store.putAwayProjectRun() }
            )
        }
    }

    /// The run's Activity details: the one view of a run (#5561).
    private func showDetails(_ jobId: String) {
        ActivityWindowSelectionState.shared.select(ActivitySelection(jobId: jobId, libraryId: libraryId))
        openWindow(id: ActivityWindowSelectionState.detailWindowID)
    }
}

/// One strip, drawn from its words.
struct ProjectRunStripRow: View {
    let strip: ProjectRunStrip
    let failure: String?
    /// A stage's Read Again target (`ActivityRunMenuTarget.stage`): the shared item Activity renders (#5652).
    let readAgain: (_ threadId: String, _ offer: String) -> ActivityRunMenuTarget
    /// What the run missed, run again on its folder (nil, the project): plain Start (#6170).
    var runAgain: (_ folderId: String?) -> Void = { _ in }
    let onShowDetails: () -> Void
    let onClose: () -> Void

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            if strip.isLive {
                ProgressView().controlSize(.small)
            } else {
                Image(systemName: strip.failed.isEmpty ? "checkmark.circle" : "exclamationmark.triangle")
                    .foregroundStyle(strip.failed.isEmpty ? Color.secondary : Color.orange)
            }
            Text(strip.title).font(.callout.weight(.semibold))
            Text(failure ?? strip.detail)
                .font(.callout)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .truncationMode(.tail)
                .help(failure ?? strip.detail)
            Spacer(minLength: 8)
            ForEach(strip.failed) { stage in
                if let offer = stage.offer {
                    ActivityReadAgainMenuItem(target: readAgain(stage.threadId, offer))
                        .labelStyle(.titleOnly)
                        .controlSize(.small)
                        .help(stage.text)
                        .accessibilityIdentifier("project.runStrip.readAgain")
                }
            }
            if let missed = strip.missed, let offer = missed.offer {
                Button(offer) { runAgain(missed.folderId) }
                    .controlSize(.small)
                    .help(missed.words)
                    .accessibilityIdentifier("project.runStrip.runAgainOnMissed")
            }
            Button("Show Details", action: onShowDetails)
                .controlSize(.small)
                .accessibilityIdentifier("project.runStrip.details")
            if !strip.isLive {
                Button("Close", systemImage: "xmark", action: onClose)
                    .labelStyle(.iconOnly)
                    .buttonStyle(.borderless)
                    .controlSize(.small)
                    .accessibilityIdentifier("project.runStrip.close")
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(.bar)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("project.runStrip")
    }
}

#Preview("Running") {
    ProjectRunStripRow(
        strip: ProjectRunStrip(
            jobId: "run-1", isLive: true, title: "Transcribe (Kraken) · stage 1 of 3",
            detail: "40 done · 2 failed · 158 left · 12 min left · Waiting: memory is tight"),
        failure: nil, readAgain: { .stage(threadId: $0, offer: $1, store: nil, report: { _ in }) },
        onShowDetails: {}, onClose: {}
    )
    .frame(width: 720)
}

#Preview("Ended with failed pages") {
    ProjectRunStripRow(
        strip: ProjectRunStrip(
            jobId: "run-1", isLive: false, title: "Recipe run failed",
            detail: "Read 198 of 203 pages · Names: 120 People · 40 Places · 35 dates · 80 statements",
            failed: [ActivityDetails.Summary.Failed(
                id: "thread-1", text: "Transcribe (Kraken): 5 pages failed",
                offer: "Read the 5 pages that failed", threadId: "thread-1")]),
        failure: nil, readAgain: { .stage(threadId: $0, offer: $1, store: nil, report: { _ in }) },
        onShowDetails: {}, onClose: {}
    )
    .frame(width: 720)
}
