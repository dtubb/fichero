import SwiftUI

/// Trailing (Xcode-style) toolbar activity indicator (startup-transport-ux
/// S1). Aggregates every source of "something is running in the
/// background" into one small glyph + tap-for-detail popover, rather than
/// each source growing its own pill:
///   • running workflow executions (`WorkflowExecutionObserver`)
///   • the per-library backend-work signal (`ActivityStore.backendWork`) —
///     imports/batches/indexing the engine or CLI kicked off out of band
///   • the in-window document import (`ContentView`'s own `isImporting` /
///     `importProgress` / `importError` state, unchanged from before)
///
/// Idle renders nothing — this item stays unobtrusive. Hosted by the
/// unconditionally-declared `ContentToolbarID.activityStatus` item in
/// `ContentView+Toolbar.swift`; only this view's CONTENT should ever vary,
/// never the `ToolbarItem` itself (#3163 guard — see
/// `EngineStatusToolbarItem`'s doc comment for why).
struct ActivityStatusToolbarItem: View {
    @Environment(WorkflowExecutionObserver.self) private var executionObserver
    @Environment(ActivityStore.self) private var activityStore
    @Environment(\.openWindow) private var openWindow

    let isImporting: Bool
    let importProgress: String?
    let libraryId: UUID
    let libraryName: String
    @Binding var importError: String?

    @State private var showPopover = false

    private var activeWorkflows: [WorkflowExecution] {
        Array(executionObserver.activeExecutions.values)
    }

    /// Count of distinct active tasks — workflows + the single backend-work
    /// slot + the in-window import + live background jobs (embedding, HTR,
    /// Detect Regions, …) from `/api/activity/jobs`. Drives the badge in the
    /// glyph and the popover's row list. Background jobs are folded in here so
    /// this popover and the full Activity viewer show the SAME work.
    private var activeCount: Int {
        activeWorkflows.count
            + (activityStore.backendWork != nil ? 1 : 0)
            + (isImporting ? 1 : 0)
            + activityStore.activeJobs.count
    }

    /// An in-window import error OR any background job the backend reports as
    /// FAILED — a failed Kraken "Detect Regions" must light the error glyph so
    /// it isn't re-run in the dark (Daniel ran it three times).
    private var hasError: Bool {
        importError != nil || !activityStore.failedJobs.isEmpty
    }

    var body: some View {
        Group {
            if hasError {
                Button {
                    showPopover = true
                } label: {
                    Image(systemName: ToolbarSymbols.activityError)
                        .foregroundStyle(.red)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Activity error")
                .help("A background task reported an error — click for details")
            } else if activeCount > 0 {
                Button {
                    showPopover = true
                } label: {
                    HStack(spacing: 4) {
                        ProgressView()
                            .controlSize(.small)
                        if activeCount > 1 {
                            Text("\(activeCount)")
                                .font(.caption2.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Active tasks")
                .help("Active tasks — click to view")
            } else {
                // Idle: subtle persistent glyph so the status island always
                // has its right button — the popover shows "Nothing running."
                // The glyph is the sidebar's Activity symbol, NOT the old
                // `list.bullet.circle`, which was indistinguishable from the
                // filter control's three-lines-in-a-circle at toolbar size
                // (#4360).
                Button {
                    showPopover = true
                } label: {
                    // Lit while its popover is open, same rule as the server
                    // button beside it (Daniel, 2026-09-02).
                    Label("Activity", systemImage: ToolbarSymbols.activityIdle)
                        .foregroundStyle(showPopover
                            ? AnyShapeStyle(Color.accentColor) : AnyShapeStyle(.secondary))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Activity")
                .help("Background activity — click to view")
            }
        }
        .popover(isPresented: $showPopover) {
            popoverContent
        }
        .accessibilityLabel(accessibilityLabel)
    }

    @ViewBuilder
    private var popoverContent: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Activity")
                .font(.headline)
            Text(libraryName)
                .font(.caption)
                .foregroundStyle(.secondary)

            if let importError {
                HStack {
                    Label(importError, systemImage: "exclamationmark.circle.fill")
                        .font(.callout)
                        .foregroundStyle(.red)
                    Spacer()
                    Button("Dismiss") { self.importError = nil }
                        .buttonStyle(.borderless)
                }
            }

            if isImporting {
                Label(importProgress ?? "Importing…", systemImage: "square.and.arrow.down")
                    .font(.callout)
            }

            if let backendWork = activityStore.backendWork {
                BackendWorkPill(status: backendWork)
            }

            // Live background jobs (embedding, derivative/HTR queues, Kraken
            // Detect Regions, …) from `/api/activity/jobs` — the SAME rows the
            // full Activity viewer shows, from the SAME source, so the two
            // surfaces can't disagree. Failed jobs render red here too.
            ForEach(activityStore.backgroundJobs) { job in
                ActivityJobRow(job: job)
            }

            ForEach(activeWorkflows, id: \.threadId) { execution in
                HStack(spacing: 8) {
                    ProgressView()
                        .controlSize(.small)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(execution.name)
                            .font(.callout)
                            .lineLimit(1)
                        if let step = execution.currentNodeName {
                            Text(step)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }
                }
            }

            if activeCount == 0 && !hasError && activityStore.backgroundJobs.isEmpty {
                Text("Nothing running.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }

            // Process CPU% from the same jobs read — what's consuming compute,
            // in the surface where the user is already looking at the work.
            if let cpu = activityStore.processCpuPercent {
                ProcessCPULabel(percent: cpu, cpuCount: activityStore.cpuCount)
            }

            Divider()

            Button("Open Activity") {
                showPopover = false
                ActivityWindowSelectionState.shared.selectLibrary(libraryId)
                openWindow(id: ActivityWindowSelectionState.monitorWindowID)
            }
        }
        .padding(14)
        .frame(minWidth: 260, alignment: .leading)
    }

    private var accessibilityLabel: String {
        if let importError { return importError }
        // A failed background job is the case this glyph exists to make audible
        // as well as visible — name it rather than saying "Import error".
        let failed = activityStore.failedJobs
        if let first = failed.first {
            return failed.count == 1 ? "\(first.name) failed" : "\(failed.count) background tasks failed"
        }
        if activeCount > 0 { return "\(activeCount) task\(activeCount == 1 ? "" : "s") running" }
        return "No activity"
    }
}
