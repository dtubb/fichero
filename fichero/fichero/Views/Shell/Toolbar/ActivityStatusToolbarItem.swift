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
    /// OPTIONAL on purpose (#4703): this view can update from a host that does not
    /// inherit the window's environment (toolbar item / inspector column) — a
    /// non-optional read here trapped the app ~25 s after launch when restored scene
    /// state re-rooted the content tree. Degrade; never trap.
    @Environment(WorkflowExecutionObserver.self) private var executionObserver: WorkflowExecutionObserver?
    @Environment(ActivityStore.self) private var activityStore
    @Environment(\.openWindow) private var openWindow

    let isImporting: Bool
    let importProgress: String?
    let libraryId: UUID
    let libraryName: String
    @Binding var importError: String?

    @State private var showPopover = false
    /// The failures the popover may show, fixed as it opens (#5666): the last hour, or since it was last opened.
    @State private var errorWindow = ActivityErrorWindow()
    private let errorLedger = ActivityErrorLedger.shared

    private var activeWorkflows: [WorkflowExecution] {
        executionObserver.map { Array($0.activeExecutions.values) } ?? []
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
    /// The red glyph is for a failure the popover would still show (#5666), not every failure ever listed.
    private var hasError: Bool {
        let window = errorLedger.window()
        return importError != nil || activityStore.failedJobs.contains { window.isRecent($0.id) }
    }

    var body: some View {
        // The Start / Stop control sits beside the indicator (ruled 2026-10-09,
        // `activity.mode.start-stop`): its state at a glance, running, held or paused.
        HStack(spacing: 6) {
            ActivityModeButton(store: activityStore)
            indicator
        }
    }

    private var indicator: some View {
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
        // When each failure failed: the engine's failed_at, or (without one) when it was first seen.
        .onChange(of: activityStore.failedJobs, initial: true) { _, jobs in errorLedger.note(failed: jobs) }
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

            // A summary, not a list (`activity.popover.summary`, #5415): the
            // rows themselves are the Activity window's.
            ActivityPopoverSummaryView(
                summary: summary,
                nothingElseRunning: !isImporting && activityStore.backendWork == nil,
                openDetails: { jobId in
                    // A failure's row opens Activity's details for that job.
                    showPopover = false
                    ActivityWindowSelectionState.shared.select(ActivitySelection(jobId: jobId, libraryId: libraryId))
                    openWindow(id: ActivityWindowSelectionState.detailWindowID)
                }
            )

            Divider()

            Button("Open Activity") {
                showPopover = false
                ActivityWindowSelectionState.shared.selectLibrary(libraryId)
                openWindow(id: ActivityWindowSelectionState.monitorWindowID)
            }
        }
        .padding(14)
        // A bounded width, so an error or a stage's wait wraps instead of running past the edge (#5666).
        .frame(minWidth: 260, maxWidth: 360, alignment: .leading)
        .accessibilityIdentifier("activity.popover")
        // Recent errors only (#5666): the window is fixed as the popover opens, and what it could show is seen
        // when it closes, so an error shows once and never piles up.
        .onAppear {
            errorLedger.note(failed: activityStore.failedJobs)
            errorWindow = errorLedger.window()
        }
        .onDisappear { errorLedger.markSeen(activityStore.failedJobs) }
        // A recipe run in hand reads as one run with its stages: its tree, read once when shown (the store
        // follows it from then on, as the Activity window's rows do).
        .task {
            for job in activityStore.backgroundJobs
            where job.taskType == ActivityStore.recipeRunKind && job.parentId == nil && !job.id.hasPrefix("waiting:") {
                await activityStore.loadRunTree(threadId: job.id)
            }
        }
    }

    private var summary: ActivityPopoverSummary {
        ActivityPopoverSummary(
            jobs: activityStore.backgroundJobs,
            paused: activityStore.backgroundPaused,
            machine: activityStore.machine,
            liveRuns: activeWorkflows.map {
                .init(id: $0.threadId, name: $0.name, step: $0.currentNodeName)
            },
            runTrees: activityStore.runTrees,
            // The process CPU from the same jobs read joins the Mac's row of symbols (#5635).
            processCpuPercent: activityStore.processCpuPercent,
            cpuCount: activityStore.cpuCount,
            errorWindow: errorWindow,
            activity: activityStore.activitySummary
        )
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
