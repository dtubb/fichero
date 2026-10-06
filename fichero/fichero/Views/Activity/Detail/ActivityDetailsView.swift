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
    @State private var trace: TraceSubject?
    @State private var actionFailure: String?

    private var details: ActivityDetails? { ActivityDetails(store: store, selection: selection) }

    var body: some View {
        Group {
            if let details {
                content(details)
            } else {
                ContentUnavailableView(
                    "Reading the Row",
                    systemImage: "clock",
                    description: Text("The engine has not answered for this row yet.")
                )
            }
        }
        // The tree this row needs, read once; later reads are the table's own.
        .task(id: selection) { await store.loadDetails(jobId: selection.jobId) }
        .sheet(item: $trace) { subject in
            RunTraceSheet(threadId: subject.threadId)
        }
        .accessibilityIdentifier("activity.details")
    }

    private func content(_ details: ActivityDetails) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                ActivityDetailsHeading(details: details)
                if let counts = details.counts {
                    ActivityDetailsProgress(counts: counts)
                }
                if !details.failedPages.isEmpty {
                    ActivityDetailsFailedPages(details: details)
                }
                ActivityDetailsActions(details: details, perform: { action in Task { await perform(action, details) } })
                if let actionFailure {
                    Label(actionFailure, systemImage: "exclamationmark.triangle.fill")
                        .font(.callout)
                        .foregroundStyle(.orange)
                }
                ActivityDetailsLog(jobId: details.jobId, isLive: details.isLive, refreshKey: details.logKey)
                if !details.resources.isEmpty {
                    ActivityDetailsResources(resources: details.resources)
                }
            }
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func perform(_ action: ActivityDetails.Action, _ details: ActivityDetails) async {
        let row = details.row
        var failure: String?
        switch action {
        case .control(let control):
            guard let jobId = row.jobId else { return }
            switch control {
            case .pause: failure = await store.setJobPaused(jobId: jobId, paused: true, runThreadId: row.runThreadId)
            case .resume: failure = await store.setJobPaused(jobId: jobId, paused: false, runThreadId: row.runThreadId)
            case .stop: failure = await store.cancelJob(jobId: jobId, runThreadId: row.runThreadId)
            }
            failure = failure.map { "Couldn't \(control.label.lowercased()) \(row.name): \($0)" }
        case .readAgain:
            guard let threadId = details.runThreadId else { return }
            failure = await store.readPagesAgain(runThreadId: threadId)
                .map { "Couldn't read the pages again: \($0)" }
        case .openPage(let documentId):
            UIVerbs.openNode(documentId)
        case .showPages(let ids):
            do {
                try UIVerbs.selectNodes(ids)
            } catch {
                failure = "Couldn't show the pages: open the project's window first."
            }
        case .showTrace(let threadId):
            trace = TraceSubject(threadId: threadId)
        }
        actionFailure = failure
    }
}

/// The run whose trace sheet is open.
private struct TraceSubject: Identifiable {
    let threadId: String
    var id: String { threadId }
}

// MARK: - Sections (small, so each type-checks quickly)

/// What the row is, by name, and its state with why.
private struct ActivityDetailsHeading: View {
    let details: ActivityDetails

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(details.heading, systemImage: details.row.kindSymbol)
                .font(.title3)
                .accessibilityIdentifier("activity.details.heading")
            if !details.subheading.isEmpty {
                Text(details.subheading.joined(separator: " · "))
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            HStack(spacing: 6) {
                Image(systemName: details.row.phase.symbol)
                    .foregroundStyle(details.row.phase == .failed ? Color.red : Color.secondary)
                    .accessibilityHidden(true)
                Text(details.stateText)
                    .font(.headline)
                    .foregroundStyle(details.row.phase == .failed ? AnyShapeStyle(.red) : AnyShapeStyle(.primary))
                    .textSelection(.enabled)
                    .accessibilityIdentifier("activity.details.state")
            }
            if let machine = details.machineText {
                Text(machine)
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

/// Pages done, failed and left, a bar, and the time left at the pace so far.
private struct ActivityDetailsProgress: View {
    let counts: ActivityDetails.Counts

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ProgressView(value: counts.fraction)
                .accessibilityLabel("Progress")
                .accessibilityValue(counts.text)
            HStack {
                Text(counts.text)
                    .monospacedDigit()
                    .accessibilityIdentifier("activity.details.counts")
                Spacer()
                if let timeLeft = counts.timeLeft {
                    Text("About \(timeLeft) left")
                        .foregroundStyle(.secondary)
                }
            }
            .font(.callout)
        }
    }
}

/// The failed pages under the row, by name, each with its reason.
private struct ActivityDetailsFailedPages: View {
    let details: ActivityDetails

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(details.failedCount == 1 ? "1 page failed" : "\(details.failedCount) pages failed")
                .font(.headline)
            ForEach(details.failedPages) { page in
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(page.name).font(.body.weight(.medium))
                    Text(page.reason)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
                .font(.callout)
            }
            if details.failedCount > details.failedPages.count {
                Text("and \(details.failedCount - details.failedPages.count) more")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
        }
        .accessibilityIdentifier("activity.details.failedPages")
    }
}

/// The row's actions; one that does not apply is absent, not disabled.
private struct ActivityDetailsActions: View {
    let details: ActivityDetails
    let perform: (ActivityDetails.Action) -> Void

    var body: some View {
        if !details.actions.isEmpty {
            HStack(spacing: 8) {
                ForEach(details.actions, id: \.self) { action in
                    Button { perform(action) } label: {
                        Label(Self.label(action), systemImage: Self.symbol(action))
                    }
                    .accessibilityIdentifier("activity.details.action.\(Self.identifier(action))")
                }
            }
            .controlSize(.small)
        }
    }

    static func label(_ action: ActivityDetails.Action) -> String {
        switch action {
        case .control(let control): control.label
        case .readAgain(let label): label
        case .openPage: "Open the Page"
        case .showPages: "Show the Pages"
        case .showTrace: "Show the Trace"
        }
    }

    static func symbol(_ action: ActivityDetails.Action) -> String {
        switch action {
        case .control(let control): control.systemImage
        case .readAgain: "arrow.clockwise"
        case .openPage: "doc.text"
        case .showPages: "rectangle.stack"
        case .showTrace: "point.3.connected.trianglepath.dotted"
        }
    }

    static func identifier(_ action: ActivityDetails.Action) -> String {
        switch action {
        case .control(let control): control.rawValue
        case .readAgain: "readAgain"
        case .openPage: "openPage"
        case .showPages: "showPages"
        case .showTrace: "showTrace"
        }
    }
}

/// The row's log: only its lines and its children's, newest last, following
/// the end while the row runs, selectable and copied as plain text. The one
/// part of the view that scrolls on its own.
struct ActivityDetailsLog: View {
    let jobId: String
    let isLive: Bool
    /// Changes when the row changes (`ActivityDetails.logKey`): the log is read again then, and only then.
    let refreshKey: String
    @Environment(ActivityStore.self) private var store

    private var lines: [ActivityJobLogLine] { store.jobLogs[jobId] ?? [] }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("Log").font(.headline)
                Spacer()
                Button {
                    copyToPasteboard(lines.map(\.plainText).joined(separator: "\n"))
                } label: {
                    Label("Copy Log", systemImage: "doc.on.doc")
                }
                .controlSize(.small)
                .disabled(lines.isEmpty)
                .accessibilityIdentifier("activity.details.log.copy")
            }
            if lines.isEmpty {
                Text("Nothing written for this row yet.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            } else {
                ScrollViewReader { proxy in
                    List(lines) { line in
                        Text(line.plainText)
                            .font(.callout.monospaced())
                            .foregroundStyle(line.level == "error" ? AnyShapeStyle(.red) : AnyShapeStyle(.primary))
                            .textSelection(.enabled)
                            .id(line.id)
                    }
                    .listStyle(.plain)
                    .frame(minHeight: 120, idealHeight: 220, maxHeight: 320)
                    .onAppear { scrollToEnd(proxy) }
                    .onChange(of: lines.count) { _, _ in
                        // Following the end while the row runs; a finished row's log stays put.
                        if isLive { scrollToEnd(proxy) }
                    }
                }
            }
        }
        .accessibilityIdentifier("activity.details.log")
        .task(id: refreshKey) { await store.loadJobLog(jobId: jobId) }
    }

    private func scrollToEnd(_ proxy: ScrollViewProxy) {
        if let last = lines.last?.id { proxy.scrollTo(last, anchor: .bottom) }
    }

    private func copyToPasteboard(_ text: String) {
        PlatformPasteboard.writeString(text)
    }
}

/// The log of the selected row alone: the Reader pane of the `.activity`
/// mode, beside the details in the Preview pane (#5561).
struct ActivityDetailsLogPane: View {
    let selection: ActivitySelection
    @Environment(ActivityStore.self) private var store

    var body: some View {
        let details = ActivityDetails(store: store, selection: selection)
        ScrollView {
            ActivityDetailsLog(
                jobId: details?.jobId ?? selection.jobId,
                isLive: details?.isLive ?? false,
                refreshKey: details?.logKey ?? selection.jobId
            )
            .padding()
        }
        .task(id: selection) { await store.loadDetails(jobId: selection.jobId) }
    }
}

/// Started, finished, elapsed, tokens, cost and peak memory; what the engine
/// did not measure is left out.
private struct ActivityDetailsResources: View {
    let resources: [ActivityDetails.Resource]

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Resources").font(.headline)
            Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 2) {
                ForEach(resources) { resource in
                    GridRow {
                        Text(resource.label).foregroundStyle(.secondary)
                        Text(resource.value).monospacedDigit().textSelection(.enabled)
                    }
                }
            }
            .font(.callout)
        }
        .accessibilityIdentifier("activity.details.resources")
    }
}

#Preview("A waiting job of its own") {
    let row = ActivityMonitorRow.job(
        ActivityJob(id: "embed-1", taskType: "embedding", name: "Embedding queue", current: 4, total: 10,
                    state: .waiting, reason: "Waiting: memory is tight"),
        libraryId: nil, projectName: "Marshall Diaries")
    let details = ActivityDetails(row: row, node: nil, runRow: nil, projectName: "Marshall Diaries",
                                  startedBy: "automatic", machine: nil)
    return VStack(alignment: .leading, spacing: 16) {
        ActivityDetailsHeading(details: details)
        if let counts = details.counts { ActivityDetailsProgress(counts: counts) }
        ActivityDetailsResources(resources: [
            .init(label: "Started", value: "14:02"), .init(label: "Elapsed", value: "4m 10s"),
            .init(label: "Cost", value: "$0.0068"), .init(label: "Peak memory, engine", value: "2.0 GB")
        ])
    }
    .padding()
    .frame(width: 480)
}
