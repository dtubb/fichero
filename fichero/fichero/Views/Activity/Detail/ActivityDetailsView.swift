import SwiftUI

/// The details of one Activity row (#5561, `activity.details.one-view`): one
/// scrolling view, no tabs, for a run, a step, a page or a job of its own.
///
/// Top to bottom: the heading by name; the state and why; pages done, failed
/// and left with the time left, the failed pages by name and the offer to read
/// them again; the row's log, newest last; its resources; its actions.
///
/// It reads the row from the project's `ActivityStore`, the record the
/// Activity table reads (`ActivityDetails`), so it follows the row: the
/// table's in-place update of the row (a tree re-read on the change stream, the
/// jobs poll) is its update. It opens no stream and no poll of its own; the
/// only read it makes is the row's log, when the row changes
/// (`activity.details.follows-the-row`).
///
/// Mounted by the ⓘ button and double-click (the Activity Details window), the
/// detail below the table, the Preview pane of the `.activity` mode and the
/// compact stack (`activity.details.one-mount`).
struct ActivityDetailsView: View {
    let selection: ActivitySelection
    @Environment(ActivityStore.self) private var store
    @Environment(AppState.self) private var appState
    @State private var trace: TraceSubject?
    @State private var actionFailure: String?
    /// The stage the page dots show; nil: each page's worst state across stages (`activity.window.page-grid`).
    @State private var gridStage: String?
    /// The live log follows its newest line while the Log is open and the page is scrolled to the end (`ActivityLogFollow`).
    @State private var atEnd = true
    @AppStorage("activity.opened.log") private var logOpen = false

    private var details: ActivityDetails? { ActivityDetails(store: store, selection: selection) }

    var body: some View {
        Group {
            if let details {
                content(details)
            } else if let failure = store.detailsReadFailure(forJobId: selection.jobId) {
                // a read that failed says so, with the engine's reason: never a pane that stays blank
                Text(failure)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .padding()
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                    .accessibilityIdentifier("activity.details.readFailure")
            } else {
                Color.clear  // nothing yet means blank (`activity.window.no-empty-prose`)
            }
        }
        // The tree this row needs, read once; later reads are the table's own.
        .task(id: selection) { await store.loadDetails(jobId: selection.jobId) }
        // A recipe run's page dots, read again when its row changes (`activity.window.page-grid`).
        .task(id: "\(details?.logKey ?? "")|\(gridStage ?? "")") {
            if let details, !details.stageCards.isEmpty { await store.loadPageGrid(jobId: details.jobId, stage: gridStage) }
        }
        .onChange(of: selection) { _, _ in gridStage = nil }
        .sheet(item: $trace) { subject in
            RunTraceSheet(threadId: subject.threadId)
        }
        .accessibilityIdentifier("activity.details")
    }

    private func content(_ details: ActivityDetails) -> some View {
        ScrollViewReader { proxy in
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                ActivityDetailsHeading(details: details)
                let bar = ActivityStageBar.segments(of: details.stageCards)
                if !bar.isEmpty { ActivityStageBar(segments: bar) }
                if let counts = details.counts {
                    ActivityDetailsProgress(counts: counts)
                }
                stagesSection(details)
                pageGridSection(details)
                if !details.failedPages.isEmpty {
                    ActivityDetailsFailedPages(details: details, readAgain: runTarget(details))
                }
                // The failed-pages section carries Read Again when it has the button; the actions row says it otherwise.
                ActivityDetailsActions(
                    details: details, hidesReadAgain: !details.failedPages.isEmpty && runTarget(details).readAgainLabel != nil,
                    run: runTarget(details),
                    perform: { action in Task { await perform(action, details) } }
                )
                footerSections(details)
                Color.clear.frame(height: 1).id(ActivityLogFollow.endAnchor)
            }
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        // Whether the person is at the end of the page: scrolling up stops the following, scrolling back down resumes it.
        .onScrollGeometryChange(for: Bool.self) { geometry in
            geometry.contentOffset.y + geometry.containerSize.height >= geometry.contentSize.height - 24
        } action: { _, nowAtEnd in
            atEnd = nowAtEnd
        }
        // The live log follows its newest line (`activity.window.open-a-run`); a finished run's stays put.
        .onChange(of: store.jobLogs[details.jobId]?.last?.id) { _, _ in
            if ActivityLogFollow.shouldFollow(isLive: details.isLive, isOpen: logOpen, atEnd: atEnd) {
                proxy.scrollTo(ActivityLogFollow.endAnchor, anchor: .bottom)
            }
        }
        // The closed Log still counts its problems: a Problems read, once per change of the row.
        .task(id: details.logKey) {
            if !logOpen { await store.loadJobLog(jobId: details.jobId, problemsOnly: true) }
        }
        }
    }

    /// A recipe run by Set Up's stages, or the older summary and stage list.
    @ViewBuilder
    private func stagesSection(_ details: ActivityDetails) -> some View {
        if !details.stageCards.isEmpty {
            // A recipe run by Set Up's stages (#5670): what each made, and why one did not run, under it.
            ActivityDetailsStageCards(
                cards: details.stageCards, perform: { action in Task { await perform(action, details) } },
                readAgain: stageTarget
            )
        } else {
            if let summary = details.summary {
                ActivityDetailsSummary(
                    summary: summary, perform: { action in Task { await perform(action, details) } },
                    readAgain: stageTarget
                )
            }
            if !details.stages.isEmpty {
                ActivityDetailsStages(stages: details.stages)
            }
        }
    }

    /// The stage chooser and the page dots (`activity.window.page-grid`).
    @ViewBuilder
    private func pageGridSection(_ details: ActivityDetails) -> some View {
        // The chooser stays while the chosen stage has no dots yet, so All stages is always one pick away.
        let ran = ActivityPageGrid.stagesThatRan(details.stageCards)
        if ran.count > 1 {
            Picker("Stage", selection: $gridStage) {
                Text("All stages").tag(String?.none)
                ForEach(ran) { Text($0.title).tag(String?.some($0.id)) }
            }
            .labelsHidden()
            .fixedSize()
            .accessibilityIdentifier("activity.details.pageGrid.stage")
        }
        if let grid = store.pageGrids[ActivityStore.pageGridKey(jobId: details.jobId, stage: gridStage)], !grid.pages.isEmpty {
            ActivityPageGridView(grid: grid, open: { UIVerbs.openNode($0) },
                                 showAll: { ids in Task { await perform(.showPages(documentIds: ids), details) } })
        }
    }

    /// Background mode, a failed action, the remote run, the queued pages, then the Details and Log disclosures.
    @ViewBuilder
    private func footerSections(_ details: ActivityDetails) -> some View {
        if details.isLive {
            // The Start / Stop control (ruled 2026-10-09): go ahead although the Mac is in use, or
            // pause all work; beside the row's own Pause and Stop (#5623).
            HStack(spacing: 6) {
                Text("Background work:").font(.callout).foregroundStyle(.secondary)
                ActivityModeButton(store: store)
            }
            .controlSize(.small)
        }
        if let actionFailure {
            Label(actionFailure, systemImage: "exclamationmark.triangle.fill")
                .font(.callout)
                .foregroundStyle(.orange)
        }
        if details.row.engineKind == "read-at-scale", let jobId = details.row.jobId {
            RemoteRunInspector(jobId: jobId, service: appState.remoteRunService)
        }
        if let kind = ActivityStore.queuedKind(ofRowId: details.jobId) {
            ActivityDetailsQueuedPages(store: store, kind: kind, rowId: details.jobId)
        }
        // Details and Log are closed until opened and remembered (`activity.window.open-a-run`).
        if !details.resources.isEmpty {
            ActivityDetailsDisclosure("Details", key: "activity.opened.details") {
                ActivityDetailsResources(resources: details.resources, titled: false)
            }
        }
        ActivityDetailsDisclosure("Log", detail: ActivityLogFilter.problemCountWords(store.jobLogProblemCount[details.jobId] ?? 0),
                                  key: "activity.opened.log") {
            ActivityDetailsLog(jobId: details.jobId, isLive: details.isLive, refreshKey: details.logKey, titled: false)
        }
    }

    /// Stop and Read Again on this row: the target the shared items act through (#5652), made as the
    /// Activity table makes it; Read Again is the run's offer as the actions word it.
    private func runTarget(_ details: ActivityDetails) -> ActivityRunMenuTarget {
        let row = details.row
        var offer: String?
        for action in details.actions {
            if case .readAgain(let label) = action { offer = label }
        }
        return .make(
            rowId: row.id, rowName: row.name, canStop: row.controls.contains(.stop),
            jobId: row.jobId, runThreadId: details.runThreadId, readAgainLabel: offer,
            store: store, report: { actionFailure = $0 }
        )
    }

    /// One stage's failed pages, read again through the shared item's target (#5652).
    private func stageTarget(threadId: String, offer: String) -> ActivityRunMenuTarget {
        .stage(threadId: threadId, offer: offer, store: store, report: { actionFailure = $0 })
    }

    /// Pause, Resume, Retry or Carry On on this row; the failure in words, nil when it went through.
    private func performControl(_ control: ActivityMonitorRow.Control, row: ActivityMonitorRow) async -> String? {
        guard let jobId = control.isRetry ? row.retryJobId : row.jobId else { return nil }
        let failure: String?
        switch control {
        case .pause: failure = await store.setJobPaused(jobId: jobId, paused: true, runThreadId: row.runThreadId)
        case .resume: failure = await store.setJobPaused(jobId: jobId, paused: false, runThreadId: row.runThreadId)
        case .stop: return nil
        case .retry, .carryOn: failure = await store.retryJob(jobId: jobId, runThreadId: row.runThreadId)
        }
        return failure.map { "Couldn't \(control.label.lowercased()) \(row.name): \($0)" }
    }

    private static func showPages(_ ids: [String]) -> String? {
        do {
            try UIVerbs.selectNodes(ids)
            return nil
        } catch {
            return "Couldn't show the pages: open the project's window first."
        }
    }

    private func openSetUp(_ stage: String?) -> String? {
        guard let libraryId = selection.libraryId else {
            return "Couldn't open the project's setup: open it with Project › Set Up…"
        }
        LibraryManager.shared.requestSetUp(for: libraryId, stage: stage)
        return nil
    }

    private func perform(_ action: ActivityDetails.Action, _ details: ActivityDetails) async {
        let row = details.row
        var failure: String?
        switch action {
        case .control(.stop):
            runTarget(details).stop()
            return
        case .control(let control):
            failure = await performControl(control, row: row)
        case .readAgain:
            runTarget(details).readAgain()
            return
        case .openPage(let documentId):
            UIVerbs.openNode(documentId)
        case .showPages(let ids):
            failure = Self.showPages(ids)
        case .showTrace(let threadId):
            trace = TraceSubject(threadId: threadId)
        case .readStageAgain(let threadId, let label):
            stageTarget(threadId: threadId, offer: label).readAgain()
            return
        case .retryDownload(let jobId):
            failure = await store.retryJob(jobId: jobId, runThreadId: row.runThreadId)
                .map { "Couldn't retry the download: \($0)" }
        case .useNextCandidate(let steps, let card):
            failure = await store.useNextCandidate(steps: steps, card: card)
                .map { "Couldn't use the next reader: \($0)" }
        case .openSetUp(let stage):
            failure = openSetUp(stage)
        case .runAgainOnMissed(let folderId, _):
            if let libraryId = selection.libraryId {
                failure = await LibraryManager.shared.runAgainOnMissed(for: libraryId, folderId: folderId)
            } else {
                failure = "Couldn't run it again: open the project and use Project › Start"
            }
        }
        actionFailure = failure
    }
}

/// The run whose trace sheet is open.
private struct TraceSubject: Identifiable {
    let threadId: String
    var id: String { threadId }
}

#Preview("Details, row not read yet") {
    let apiClient = APIClient()
    ActivityDetailsView(selection: ActivitySelection(jobId: "preview"))
        .environment(ActivityStore(service: ActivityService(apiClient: apiClient), projectKey: "preview"))
        .environment(AppState())
        .frame(width: 360, height: 240)
}
