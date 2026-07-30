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
    /// Optional: the Activity window can open without a library (previews,
    /// early launch), and an import row simply doesn't apply then (#4203).
    @Environment(LibraryManager.self) private var libraryManager: LibraryManager?

    @State private var selection: ActivityMonitorRow.ID?
    @State private var logRun: SelectedActivityRun?
    @State private var errorMessage: String?

    private var activeImportService: ImportService? {
        libraryManager?.importingLibrary?.importService
    }

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

    // The alert sits on its OWN node, outside the sheet's: stacking two
    // presentation modifiers on one node is the duplicate-registration shape
    // that crashed the app at launch when `.searchable` registered twice
    // (#3163). Same rendering, one presentation per node. (#4201)
    var body: some View {
        monitorContent
            .alert("Action Failed", isPresented: Binding(
                get: { errorMessage != nil },
                set: { if !$0 { errorMessage = nil } }
            )) {
                Button("OK") { errorMessage = nil }
            } message: {
                if let errorMessage { Text(errorMessage) }
            }
    }

    private var monitorContent: some View {
        VStack(spacing: 0) {
            // An import is activity too (#4203): a folder drop used to show
            // nothing anywhere until it finished. It sits ABOVE the workflow
            // table because it's the transient thing the user is waiting on.
            if let importService = activeImportService,
               let ingest = importService.activeIngest {
                IngestProgressView(
                    status: ingest,
                    libraryName: importService.activeIngestLibraryName,
                    onCancel: { Task { await importService.cancelActiveIngest() } }
                )
                .padding(.horizontal, 12)
                .padding(.top, 8)
                Divider()
                    .padding(.top, 8)
            }
            monitorTableContent
        }
    }

    private var monitorTableContent: some View {
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

            // ONE control component over ONE status vocabulary (#4321):
            // Monitor and Detail render the same buttons, and every action is
            // transactional through WorkflowExecutionStore.perform — the row
            // updates (or disappears, on Delete) when the POST lands.
            if let execution = selectedExecution {
                RunControls(
                    threadId: execution.threadId,
                    status: execution.status,
                    onError: { errorMessage = $0 }
                )
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

        let service = ActivityService(apiClient: apiClient)
        let items = (try? await service.queryActivities(limit: 100)) ?? []
        var seen = Set<String>()
        for item in items {
            guard let threadId = item.threadId, seen.insert(threadId).inserted else { continue }
            await store.seedFromPersistedRun(threadId: threadId)
            // Subscribe any NON-TERMINAL run — paused included (#4321): a
            // paused run was never subscribed, so a later Resume had no stream
            // to carry the transition and could never visibly work.
            if let execution = store.execution(forThreadId: threadId),
               WorkflowExecutionStore.shouldSubscribe(status: execution.status) {
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
