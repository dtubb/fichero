import OSLog
import SwiftUI

private let monitorLogger = Logger(subsystem: "app.fichero.fichero", category: "ActivityMonitorView")

/// THE live workflow monitor (#2546 / B2): a hierarchical outline `Table`
/// driven by the shared, threadId-keyed `WorkflowExecutionStore`.
///
/// Three levels — run → nodes → files the running node is working on — rendered
/// with `DisclosureTableRow`. It observes the store directly, so every SSE event
/// the store reduces re-renders the table live. Used as the root of the
/// poppable "Activity" window (`ActivityMonitorWindow`); the in-sidebar Activity
/// browser/detail surface stays as-is.
struct ActivityMonitorView: View {
    /// Shared live-execution store (#2546). Optional so the view never crashes
    /// where the store isn't injected (e.g. previews).
    @Environment(WorkflowExecutionStore.self) private var store: WorkflowExecutionStore?

    /// Used by the "Get Log" sheet (`ActivityLogView`) and to seed any live runs
    /// this process already knows about into the store.
    @Environment(WorkflowExecutionObserver.self) private var observer
    @Environment(APIClient.self) private var apiClient

    @State private var selection: ActivityMonitorRow.ID?
    @State private var logRun: SelectedActivityRun?
    @State private var isActing = false
    @State private var errorMessage: String?

    private var rows: [ActivityMonitorRow] {
        guard let store else { return [] }
        return ActivityMonitorRow.rows(from: Array(store.executions.values))
    }

    /// The run that owns the current selection (works for any selected level).
    /// Row ids are `kind:threadId[:childId]`, so the threadId is the 2nd field.
    private var selectedExecution: WorkflowExecution? {
        guard let selection, let store else { return nil }
        let parts = selection.split(separator: ":")
        guard parts.count >= 2 else { return nil }
        return store.execution(forThreadId: String(parts[1]))
    }

    var body: some View {
        Group {
            if rows.isEmpty {
                ContentUnavailableView(
                    "No Activity",
                    systemImage: "chart.bar.doc.horizontal",
                    description: Text("Run a workflow to watch it here.")
                )
            } else {
                monitorTable
            }
        }
        .toolbar { monitorToolbar }
        .sheet(item: $logRun) { run in logSheet(run) }
        .alert("Action Failed", isPresented: Binding(
            get: { errorMessage != nil },
            set: { if !$0 { errorMessage = nil } }
        )) {
            Button("OK") { errorMessage = nil }
        } message: {
            if let errorMessage { Text(errorMessage) }
        }
        .task { await populate() }
    }

    // MARK: - Table

    private var monitorTable: some View {
        Table(of: ActivityMonitorRow.self, selection: $selection) {
            TableColumn("Name") { row in
                Text(row.name).lineLimit(1)
            }
            .width(min: 180, ideal: 280)

            TableColumn("Status") { row in
                statusCell(row)
            }
            .width(50)

            TableColumn("Progress") { row in
                progressCell(row)
            }
            .width(min: 80, ideal: 120)

            TableColumn("Detail") { row in
                Text(row.detail)
                    .font(.callout.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            .width(min: 90, ideal: 140)
        } rows: {
            ForEach(rows) { run in
                DisclosureTableRow(run) {
                    ForEach(run.children ?? []) { node in
                        if let files = node.children, !files.isEmpty {
                            DisclosureTableRow(node) {
                                ForEach(files) { file in
                                    TableRow(file)
                                }
                            }
                        } else {
                            TableRow(node)
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func statusCell(_ row: ActivityMonitorRow) -> some View {
        if row.isSpinning {
            ProgressView()
                .controlSize(.small)
        } else {
            Image(systemName: row.statusSymbol)
                .foregroundStyle(row.statusColor)
        }
    }

    @ViewBuilder
    private func progressCell(_ row: ActivityMonitorRow) -> some View {
        if let progress = row.progress {
            ProgressView(value: progress)
                .controlSize(.small)
        } else {
            Text("—").foregroundStyle(.tertiary)
        }
    }

    // MARK: - Toolbar (actions on the selected run)

    @ToolbarContentBuilder
    private var monitorToolbar: some ToolbarContent {
        ToolbarItemGroup {
            Button {
                openLog()
            } label: {
                Label("Get Log", systemImage: "doc.text")
            }
            .disabled(selectedExecution == nil)

            if let execution = selectedExecution {
                switch execution.status {
                case .running:
                    Button {
                        Task { await act(.pause) }
                    } label: {
                        Label("Pause", systemImage: "pause")
                    }
                    .disabled(isActing)

                    Button {
                        Task { await act(.stop) }
                    } label: {
                        Label("Stop", systemImage: "stop")
                    }
                    .disabled(isActing)
                case .paused:
                    Button {
                        Task { await act(.resume) }
                    } label: {
                        Label("Resume", systemImage: "play.fill")
                    }
                    .disabled(isActing)

                    Button {
                        Task { await act(.stop) }
                    } label: {
                        Label("Stop", systemImage: "stop")
                    }
                    .disabled(isActing)
                // Terminal / non-live states surface Delete. `.idle` is the
                // non-running case on WorkflowStatus (the switch was
                // non-exhaustive without it — #2631).
                case .completed, .failed, .idle:
                    Button {
                        Task { await act(.delete) }
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                    .disabled(isActing)
                }
            }
        }
    }

    private func logSheet(_ run: SelectedActivityRun) -> some View {
        VStack(spacing: 0) {
            HStack {
                Text(run.name).font(.headline).lineLimit(1)
                Spacer()
                Button("Done") { logRun = nil }
            }
            .padding(12)
            Divider()
            ActivityLogView(selectedRun: run)
        }
        .frame(minWidth: 520, minHeight: 420)
    }

    // MARK: - Actions

    private func openLog() {
        guard let execution = selectedExecution else { return }
        logRun = SelectedActivityRun(
            id: execution.threadId,
            name: activityCleanWorkflowName(execution.name),
            workflowId: execution.id,
            threadId: execution.threadId,
            timestamp: execution.startTime,
            status: activityMapExecutionStatus(execution.status).toStatusType(),
            isLive: execution.isRunning,
            childType: .log
        )
    }

    private func act(_ action: ActivityViewHelpers.RunAction) async {
        guard let threadId = selectedExecution?.threadId else { return }
        isActing = true
        defer { isActing = false }
        do {
            try await ActivityViewHelpers.performRunAction(action, threadId: threadId, apiClient: apiClient)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Populate

    /// Make the monitor self-populating: subscribe any live runs this process
    /// already knows (the store owns the SSE), then seed recent runs from the
    /// backend so finished/mid-flight runs appear too. Idempotent — all of the
    /// store's seed/subscribe entry points no-op when an entry exists.
    private func populate() async {
        guard let store else { return }

        for execution in observer.activeExecutions.values {
            store.subscribe(
                threadId: execution.threadId,
                workflowId: execution.id,
                name: execution.name
            )
        }

        let service = ActivityServiceGenerated(apiClient: apiClient)
        let items = (try? await service.queryActivities(limit: 100)) ?? []
        var seen = Set<String>()
        for item in items {
            guard let threadId = item.threadId, seen.insert(threadId).inserted else { continue }
            await store.seedFromPersistedRun(threadId: threadId)
            if let execution = store.execution(forThreadId: threadId), execution.status == .running {
                store.subscribe(
                    threadId: threadId,
                    workflowId: execution.id,
                    name: execution.name
                )
            }
        }
        monitorLogger.info("Activity monitor populated \(store.executions.count) run(s)")
    }
}
