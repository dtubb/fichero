import SwiftUI

// Split out of ActivityDetailsView.swift by its file_length limit (ported from m-bugs-window-c16); behaviour unchanged.

/// The row's log: only its lines and its children's, newest last, following
/// the end while the row runs, selectable and copied as plain text. The one
/// part of the view that scrolls on its own.
struct ActivityDetailsLog: View {
    let jobId: String
    let isLive: Bool
    /// Changes when the row changes (`ActivityDetails.logKey`): the log is read again then, and only then.
    let refreshKey: String
    /// With its own "Log" heading; false inside a disclosure that already says it.
    var titled = true
    @Environment(ActivityStore.self) private var store
    /// The filter row: Problems · All · Everything. Until the person chooses, Problems while the log has any problem, else All;
    /// Everything is the Developer level (`activity.log.developer-level`).
    @State private var chosen: ActivityLogFilter?
    /// The person's Everything choice is remembered, as the old Developer toggle was (`activity.log.developer-level`).
    @AppStorage("activity.log.developer") private var developer = false
    private var filter: ActivityLogFilter {
        ActivityLogFilter.effective(chosen: chosen, developer: developer, hasProblems: store.jobLogHasProblems[jobId] ?? false)
    }

    private var lines: [ActivityJobLogLine] { store.jobLogs[jobId] ?? [] }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                if titled { Text("Log").font(.headline) }
                Spacer()
                Picker("Show", selection: Binding(get: { filter }, set: { chosen = $0; developer = $0.developer })) {
                    ForEach(ActivityLogFilter.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .fixedSize()
                .controlSize(.small)
                .help("Problems: warnings and errors. All: the log. Everything: also the debug lines, as a developer reads them")
                .accessibilityIdentifier("activity.details.log.filter")
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
                // The page is ONE scroll view: the log is not a list inside another scroll (`activity.window.open-a-run`).
                LazyVStack(alignment: .leading, spacing: 2) {
                    ForEach(lines) { line in
                        Text(line.plainText)
                            .font(.callout.monospaced())
                            .foregroundStyle(line.level == "error" ? AnyShapeStyle(.red) : AnyShapeStyle(.primary))
                            .textSelection(.enabled)
                    }
                }
            }
        }
        .accessibilityIdentifier("activity.details.log")
        // A choice is about one row's log: another row starts from the default again (Everything stays, remembered).
        .onChange(of: jobId) { _, _ in chosen = nil }
        .task(id: "\(refreshKey)|\(filter.rawValue)") {
            await store.loadJobLog(jobId: jobId, developer: filter.developer, problemsOnly: filter.problemsOnly)
        }
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
struct ActivityDetailsResources: View {
    let resources: [ActivityDetails.Resource]
    var titled = true

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if titled { Text("Resources").font(.headline) }
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
