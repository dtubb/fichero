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

    /// The strip for the store's project run, or nil when there is none.
    @MainActor
    init?(store: ActivityStore) {
        guard let jobId = store.projectRunId else { return nil }
        self.init(jobId: jobId, node: store.runTrees[jobId],
                  job: store.backgroundJobs.first { $0.id == jobId })
    }

    /// Preview seam: the words given.
    init(jobId: String, isLive: Bool, title: String, detail: String, failed: [ActivityDetails.Summary.Failed] = []) {
        self.jobId = jobId
        self.isLive = isLive
        self.title = title
        self.detail = detail
        self.failed = failed
    }

    /// The strip from the run's node and its row on the jobs poll: pure, so a test can build it.
    init(jobId: String, node: ActivityJobNode?, job: ActivityJob?) {
        self.jobId = jobId
        let state = node?.state ?? (job?.state == .running ? "running" : "waiting")
        let ended = ["done", "failed", "cancelled"].contains(state)
        isLive = !ended
        if ended {
            let summary = ActivityDetails.summary(of: node)
            switch state {
            case "done": title = "Recipe run finished"
            case "cancelled": title = "Recipe run stopped"
            default: title = "Recipe run failed"
            }
            detail = summary?.lines.joined(separator: " · ") ?? (node?.reason ?? "")
            failed = summary?.failed ?? []
            return
        }
        failed = []
        let words = Self.liveWords(state: state, node: node, job: job)
        title = words.title
        detail = words.detail
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
            if let waiting = stage.waitingFor ?? node?.reason { parts.append("Waiting: \(waiting)") }
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
                onReadAgain: readAgain,
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

    /// A stage's failed pages, read again through the store's one route.
    private func readAgain(_ threadId: String) {
        Task {
            failure = await store.readPagesAgain(runThreadId: threadId)
                .map { "Couldn't read the pages again: \($0)" }
        }
    }
}

/// One strip, drawn from its words.
struct ProjectRunStripRow: View {
    let strip: ProjectRunStrip
    let failure: String?
    let onReadAgain: (String) -> Void
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
                    Button(offer) { onReadAgain(stage.threadId) }
                        .controlSize(.small)
                        .help(stage.text)
                        .accessibilityIdentifier("project.runStrip.readAgain")
                }
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
        failure: nil, onReadAgain: { _ in }, onShowDetails: {}, onClose: {}
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
        failure: nil, onReadAgain: { _ in }, onShowDetails: {}, onClose: {}
    )
    .frame(width: 720)
}
