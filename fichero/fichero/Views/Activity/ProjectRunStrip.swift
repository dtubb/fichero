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
    var missed: ActivityDetails.MissedOffer?
    /// The state the strip goes by (`effectiveState`); the preview seam's live strip runs.
    var state = "running"
    /// Set when a step of the run was paused at a cloud spend cap, as the engine says it (`stopped_at_cap`, #6295): the strip offers
    /// the caps' change by it, says its words in place of the run's own line, and the popover offers the caps it names.
    var stoppedAtCap: CloudCapFix.Stop?
    /// A spinner only while the run works now: a paused, waiting or stalled run is live but still
    /// (`activity.spinner-reflects-process-liveness`, #4346).
    var spins: Bool { isLive && state == "running" }

    /// The strip for the store's project run, or nil when there is none.
    @MainActor
    init?(store: ActivityStore) {
        guard let jobId = store.projectRunId else { return nil }
        self.init(jobId: jobId, node: store.runTrees[jobId],
                  job: store.backgroundJobs.first { $0.id == jobId },
                  folders: store.recipeRunFolders[jobId], pagesAtOnce: store.recipeRunPagesAtOnce[jobId])
        stoppedAtCap = store.recipeRunStoppedAtCap[jobId]
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
        self.state = state
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
    /// or stalled: an end, a stall or a pause in the list wins over a tree that has not caught up. Pure, tested without a store.
    nonisolated static func effectiveState(nodeState: String?, jobState: ActivityJob.State?) -> String {
        if let nodeState, ["done", "failed", "cancelled"].contains(nodeState) { return nodeState }
        switch jobState {
        case .completed: return "done"
        case .failed: return "failed"
        case .stalled: return "stalled"
        case .paused: return "paused"  // a pause in the list wins over a tree still saying running: a paused run never spins
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
            // Start's own count of what was already done, so a run on 58 of 95 pages says why (#6091).
            if let note = stage.note { parts.append(note) }
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

/// Which steps of a recipe run are done on one folder (`activity.run.folder-steps-done`, #5642), as the run's status
/// carries them (`folder_steps`), each step named by the status's own stage title. The engine counts; the app only words it.
struct RecipeFolderSteps: Equatable {
    struct Step: Equatable {
        let name: String
        /// nil: the step cannot tell which pages it has done.
        let done: Int?
        let of: Int
    }

    let steps: [Step]

    /// Each folder the status counts, by the folder's id.
    static func byFolder(_ status: Components.Schemas.RecipeRunStatus) -> [String: RecipeFolderSteps] {
        var out: [String: RecipeFolderSteps] = [:]
        for folder in status.folderSteps ?? [] {
            out[folder.folderId] = RecipeFolderSteps(steps: folder.steps.map { counted in
                let stage = status.steps.first { $0.steps == counted.steps }
                return Step(name: stage?.title ?? counted.steps.joined(separator: ", "), done: counted.done, of: counted.of)
            })
        }
        return out
    }

    var allDone: Bool { steps.allSatisfy { ($0.done ?? -1) >= $0.of } }

    /// One line a step: "Find lines and Read each line: 12 of 20 pages", "Find names: done".
    var words: String {
        steps.map { step in
            guard let done = step.done else { return "\(step.name): cannot tell" }
            return done >= step.of ? "\(step.name): done" : "\(step.name): \(done) of \(step.of) \(step.of == 1 ? "page" : "pages")"
        }.joined(separator: "\n")
    }
}

/// How many pages a recipe run reads at once now, and which hold makes it one (`recipes-run.memory.gate-shown`, #6217),
/// as the run's status carries them (`pages_at_once`, `pages_at_once_reason`). The engine decides; the app only words it.
struct RecipeRunPagesAtOnce: Equatable {
    let count: Int
    let reason: String?
    /// The threads each page reads on (#6229); nil from an engine that does not say.
    let threads: Int?

    /// nil when the status says nothing: the run is not going.
    init?(_ status: Components.Schemas.RecipeRunStatus) {
        guard let count = status.pagesAtOnce else { return nil }
        self.init(count: count, reason: status.pagesAtOnceReason, threads: status.threadsEach)
    }

    init(count: Int, reason: String?, threads: Int? = nil) {
        self.count = count
        self.reason = reason
        self.threads = threads
    }

    /// "reading 2 pages at once, 2 threads each"; "one page at a time on 4 threads: the Mac is paging".
    var words: String {
        let each = threads.map { $0 == 1 ? "1 thread" : "\($0) threads" }
        if count > 1 {
            return ["reading \(count) pages at once", each.map { "\($0) each" }].compactMap { $0 }.joined(separator: ", ")
        }
        let oneAtATime = ["one page at a time", each].compactMap { $0 }.joined(separator: " on ")
        return [oneAtATime, reason].compactMap { $0 }.joined(separator: ": ")
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
    @State private var changingCaps = false

    var body: some View {
        if let strip = ProjectRunStrip(store: store) {
            ProjectRunStripRow(
                strip: strip,
                failure: failure,
                readAgain: { threadId, offer in
                    .stage(threadId: threadId, offer: offer, store: store, report: { failure = $0 })
                },
                runAgain: { missed in
                    Task {
                        failure = await LibraryManager.shared.runAgainOnMissed(
                            for: libraryId, folderId: missed.folderId, documents: missed.documents)
                    }
                },
                onShowDetails: { showDetails(strip.jobId) },
                onClose: { store.putAwayProjectRun() },
                // A run stopped or paused at a spend cap changes the caps here, in place (#6295).
                onChangeCaps: strip.stoppedAtCap != nil ? { changingCaps = true } : nil
            )
            .popover(isPresented: $changingCaps, arrowEdge: .top) { capsPopover(for: strip.stoppedAtCap) }
        }
    }

    /// The caps to change, beside the amounts the engine says the plan needs and the ones that let the refused call through (`stop`);
    /// the plan is read when it opens.
    @ViewBuilder
    private func capsPopover(for stop: CloudCapFix.Stop?) -> some View {
        if let library = LibraryManager.shared.openLibraries.first(where: { $0.id == libraryId }) {
            CloudCapChangeView(store: library.recipeSetupStore, stop: stop, undo: library.actionsService)
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
    var runAgain: (_ missed: ActivityDetails.MissedOffer) -> Void = { _ in }
    let onShowDetails: () -> Void
    let onClose: () -> Void
    /// Change the spend caps in place: offered only when the run stopped at one (`ProjectRunStrip.stoppedAtCap`, the engine's field).
    var onChangeCaps: (() -> Void)?

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            if strip.spins {
                ProgressView().controlSize(.small)
            } else if strip.isLive {
                Image(systemName: strip.state == "paused" ? "pause.circle" : strip.state == "stalled" ? "exclamationmark.circle" : "clock")
                    .foregroundStyle(.secondary)
            } else {
                Image(systemName: strip.failed.isEmpty ? "checkmark.circle" : "exclamationmark.triangle")
                    .foregroundStyle(strip.failed.isEmpty ? Color.secondary : Color.orange)
            }
            Text(strip.title).font(.callout.weight(.semibold))
            Text(failure ?? strip.stoppedAtCap?.words ?? strip.detail)
                .font(.callout)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .truncationMode(.tail)
                .help(failure ?? strip.stoppedAtCap?.words ?? strip.detail)
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
                Button(offer) { runAgain(missed) }
                    .controlSize(.small)
                    .help(missed.words)
                    .accessibilityIdentifier("project.runStrip.runAgainOnMissed")
            }
            if let onChangeCaps {
                Button("Change the Cap…", action: onChangeCaps)
                    .controlSize(.small)
                    .accessibilityIdentifier("project.runStrip.changeCap")
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
