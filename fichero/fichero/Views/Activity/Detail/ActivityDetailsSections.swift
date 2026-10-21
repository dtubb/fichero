import SwiftUI

// MARK: - Sections (small, so each type-checks quickly)

/// What the row is, by name, and its state with why.
struct ActivityDetailsHeading: View {
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
            if let workingOn = details.workingOn {
                Label("Working on \(workingOn)", systemImage: "gearshape.2")
                    .font(.callout)
                    .textSelection(.enabled)
                    .accessibilityIdentifier("activity.details.workingOn")
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
struct ActivityDetailsProgress: View {
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
struct ActivityDetailsFailedPages: View {
    let details: ActivityDetails

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(details.failedCount == 1 ? "1 page failed" : "\(details.failedCount) pages failed")
                .font(.headline)
            ForEach(details.failedPages) { page in
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(page.title).font(.body.weight(.medium))
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

/// The pages queued behind a kind's row, in the order the lane picks them, each with its state and why
/// (`activity.window.expands-to-pages`, #5839). The first 50; it says how many more.
struct ActivityDetailsQueuedPages: View {
    let store: ActivityStore
    let kind: String
    let rowId: String
    private static let shown = 50

    var body: some View {
        let items = store.queuedItems[kind] ?? []
        VStack(alignment: .leading, spacing: 4) {
            if !items.isEmpty {
                Text(items.count == 1 ? "1 page queued" : "\(items.count) pages queued").font(.headline)
                ForEach(items) { item in
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(item.subject).font(.body.weight(.medium))
                        Text(item.reason ?? item.state).foregroundStyle(.secondary)
                    }
                    .font(.callout)
                }
                let more = store.queuedPagesNotListed(rowId: rowId, listed: items.count)
                if more > 0 {
                    Text("and \(more) more").font(.callout).foregroundStyle(.secondary)
                }
            }
        }
        .task(id: store.queueKey(forRowId: rowId)) { await store.loadQueuedItems(rowId: rowId, limit: Self.shown) }
        .accessibilityIdentifier("activity.details.queuedPages")
    }
}

/// The row's actions; one that does not apply is absent, not disabled.
struct ActivityDetailsActions: View {
    let details: ActivityDetails
    /// Stop and Read Again: the same items the Activity table and Project › Activity render (#5652).
    let run: ActivityRunMenuTarget
    let perform: (ActivityDetails.Action) -> Void

    var body: some View {
        if !details.actions.isEmpty {
            HStack(spacing: 8) {
                ForEach(details.actions, id: \.self) { action in
                    Group {
                        switch action {
                        case .control(.stop): ActivityStopMenuItem(target: run)
                        case .readAgain: ActivityReadAgainMenuItem(target: run)
                        default:
                            Button { perform(action) } label: {
                                Label(Self.label(action), systemImage: Self.symbol(action))
                            }
                        }
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
        case .readStageAgain(_, let label): label
        case .openSetUp: "Open Set Up…"
        case .retryDownload: "Retry"
        case .useNextCandidate: "Use the Next Reader"
        }
    }

    static func symbol(_ action: ActivityDetails.Action) -> String {
        switch action {
        case .control(let control): control.systemImage
        case .readAgain: "arrow.clockwise"
        case .openPage: "doc.text"
        case .showPages: "rectangle.stack"
        case .showTrace: "point.3.connected.trianglepath.dotted"
        case .readStageAgain: "arrow.clockwise"
        case .openSetUp: "slider.horizontal.3"
        case .retryDownload: "arrow.clockwise"
        case .useNextCandidate: "arrow.right.circle"
        }
    }

    static func identifier(_ action: ActivityDetails.Action) -> String {
        switch action {
        case .control(let control): control.rawValue
        case .readAgain: "readAgain"
        case .openPage: "openPage"
        case .showPages: "showPages"
        case .showTrace: "showTrace"
        case .readStageAgain: "readStageAgain"
        case .openSetUp: "openSetUp"
        case .retryDownload: "retryDownload"
        case .useNextCandidate: "useNextCandidate"
        }
    }
}

/// A recipe run's stages in order (#5576): each by name, its state and why,
/// its pages done, failed and left, its time left and what its pages wait for.
struct ActivityDetailsStages: View {
    let stages: [ActivityDetails.Stage]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Stages").font(.headline)
            ForEach(stages) { stage in
                VStack(alignment: .leading, spacing: 2) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(stage.title).font(.body.weight(.medium))
                        if !stage.steps.isEmpty {
                            Text(stage.steps).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Text(stage.state)
                        .foregroundStyle(stage.isFailed ? AnyShapeStyle(.red) : AnyShapeStyle(.secondary))
                        .textSelection(.enabled)
                    if let counts = stage.counts {
                        HStack {
                            Text(counts).monospacedDigit()
                            if let timeLeft = stage.timeLeft {
                                Text("About \(timeLeft) left").foregroundStyle(.secondary)
                            }
                        }
                    }
                    if let waiting = stage.waitingFor {
                        Label(waiting, systemImage: "hourglass").foregroundStyle(.secondary)
                    }
                }
                .font(.callout)
            }
        }
        .accessibilityIdentifier("activity.details.stages")
    }
}

/// What a recipe run made, once it has ended (#5577): pages read, names by
/// kind, dates and statements, each stage's failed pages with Read Again, and
/// the steps the plan skipped with why, and Set Up… where setup can fix one.
struct ActivityDetailsSummary: View {
    let summary: ActivityDetails.Summary
    let perform: (ActivityDetails.Action) -> Void
    /// A stage's Read Again target (`ActivityRunMenuTarget.stage`), for the shared item.
    let readAgain: (_ threadId: String, _ offer: String) -> ActivityRunMenuTarget

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("What this run made").font(.headline)
            ForEach(summary.lines, id: \.self) { line in
                Text(line).font(.callout)
            }
            ForEach(summary.failed) { stage in
                HStack(alignment: .firstTextBaseline) {
                    Label(stage.text, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
                    if let offer = stage.offer {
                        ActivityReadAgainMenuItem(target: readAgain(stage.threadId, offer))
                            .labelStyle(.titleOnly)
                            .controlSize(.small)
                            .accessibilityIdentifier("activity.details.summary.readAgain")
                    }
                }
                .font(.callout)
            }
            ForEach(summary.downloadFailed) { row in
                HStack(alignment: .firstTextBaseline) {
                    Label(row.text, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
                    Button("Retry") { perform(.retryDownload(jobId: row.retryJobId)) }
                        .controlSize(.small)
                        .accessibilityIdentifier("activity.details.summary.retryDownload")
                    if let next = row.next, let step = row.steps.first {
                        Button("Use \(next.name)") { perform(.useNextCandidate(step: step, card: next.card)) }
                            .controlSize(.small)
                            .disabled(next.needsPermission)
                            .help(next.needsPermission
                                  ? "This reader runs in the cloud: allow cloud models in Set Up first."
                                  : "Take the next reader in this step's chain")
                            .accessibilityIdentifier("activity.details.summary.useNextCandidate")
                    }
                }
                .font(.callout)
            }
            if !summary.skipped.isEmpty {
                Text("Skipped").font(.subheadline.weight(.semibold))
                ForEach(summary.skipped) { step in
                    Text(step.text).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
                }
                if summary.skipped.contains(where: \.hasFix) {
                    Button("Open Set Up…") { perform(.openSetUp(stage: nil)) }
                        .controlSize(.small)
                        .accessibilityIdentifier("activity.details.summary.setUp")
                }
            }
        }
        .accessibilityIdentifier("activity.details.summary")
    }
}
