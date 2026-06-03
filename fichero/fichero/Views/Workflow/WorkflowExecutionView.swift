import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowExecutionView")

/// View for monitoring workflow execution threads
struct WorkflowExecutionView: View {
    @EnvironmentObject var apiClient: APIClient
    @StateObject private var executionService = WorkflowExecutionService()
    @State private var selectedThread: ExecutionThread?
    @State private var isLoading = false
    @State private var cacheStats: WorkflowExecutionPayload?

    var body: some View {
        threadList
            .task {
                guard !Task.isCancelled else { return }
                // Set library path on execution service
                executionService.setLibraryPath(apiClient.currentLibraryPath)
                await loadThreads()
            }
            .refreshable {
                await loadThreads()
            }
            .sheet(item: $selectedThread) { thread in
                ThreadDetailSheet(
                    thread: thread,
                    executionService: executionService,
                    onRefresh: { await refreshThread(thread.threadId) }
                )
            }
    }

    @ViewBuilder
    private var threadList: some View {
        Group {
            if isLoading && executionService.threads.isEmpty {
                ProgressView("Loading threads...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if executionService.threads.isEmpty {
                ContentUnavailableView(
                    "No Execution Threads",
                    systemImage: "play.circle",
                    description: Text("Run a workflow to see execution threads here")
                )
            } else {
                List(executionService.threads) { thread in
                    ThreadRow(thread: thread)
                        .contentShape(Rectangle())
                        .onTapGesture(count: 2) {
                            selectedThread = thread
                        }
                        .contextMenu {
                            Button {
                                selectedThread = thread
                            } label: {
                                Label("View Details", systemImage: "info.circle")
                            }

                            if thread.status == .paused {
                                Button {
                                    Task { await resumeThread(thread.threadId) }
                                } label: {
                                    Label("Resume", systemImage: "play.fill")
                                }
                            }

                            Button(role: .destructive) {
                                Task { await deleteThread(thread.threadId) }
                            } label: {
                                Label("Delete", systemImage: "trash")
                            }
                        }
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task { await loadThreads() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(isLoading)
            }

            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task { await loadCacheStats() }
                } label: {
                    Image(systemName: "externaldrive.badge.icloud")
                }
                .disabled(isLoading)
                .help("Load workflow execution cache stats")
            }

            ToolbarItem(placement: .primaryAction) {
                Button(role: .destructive) {
                    Task { await clearAllCache() }
                } label: {
                    Image(systemName: "externaldrive.badge.xmark")
                }
                .disabled(isLoading)
                .help("Clear all workflow execution cache")
            }
        }
    }

    private func loadThreads() async {
        isLoading = true
        defer { isLoading = false }

        do {
            _ = try await executionService.listThreads()
        } catch {
            logger.error("Failed to load threads: \(String(describing: error))")
        }
    }

    private func refreshThread(_ threadId: String) async {
        do {
            let updated = try await executionService.getThreadStatus(threadId: threadId)
            selectedThread = updated
        } catch {
            logger.error("Failed to refresh thread: \(String(describing: error))")
        }
    }

    private func resumeThread(_ threadId: String) async {
        do {
            let updated = try await executionService.resumeWorkflow(threadId: threadId)
            selectedThread = updated
            await loadThreads()
        } catch {
            logger.error("Failed to resume thread: \(String(describing: error))")
        }
    }

    private func deleteThread(_ threadId: String) async {
        do {
            try await executionService.deleteThread(threadId: threadId)
            if selectedThread?.threadId == threadId {
                selectedThread = nil
            }
        } catch {
            logger.error("Failed to delete thread: \(String(describing: error))")
        }
    }

    private func loadCacheStats() async {
        do {
            cacheStats = try await executionService.getAllCacheStats()
            logger.info("Loaded workflow execution cache stats")
        } catch {
            logger.error("Failed to load workflow execution cache stats: \(String(describing: error))")
        }
    }

    private func clearAllCache() async {
        do {
            try await executionService.clearAllCache()
            cacheStats = nil
            logger.info("Cleared workflow execution cache")
        } catch {
            logger.error("Failed to clear workflow execution cache: \(String(describing: error))")
        }
    }
}

/// Row displaying a single execution thread
struct ThreadRow: View {
    let thread: ExecutionThread

    var body: some View {
        HStack {
            Image(systemName: statusIcon)
                .foregroundColor(statusColor)

            VStack(alignment: .leading, spacing: 2) {
                Text(thread.workflowName)
                    .font(.headline)

                Text(thread.threadId)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Spacer()

            Text(thread.status.rawValue.capitalized)
                .font(.caption)
                .padding(.horizontal, 8)
                .padding(.vertical, 2)
                .background(statusColor.opacity(0.2))
                .foregroundColor(statusColor)
                .cornerRadius(4)
        }
        .padding(.vertical, 4)
    }

    private var statusIcon: String {
        switch thread.status {
        case .running:
            return "play.circle.fill"
        case .paused:
            return "pause.circle.fill"
        case .completed:
            return "checkmark.circle.fill"
        case .failed:
            return "exclamationmark.circle.fill"
        }
    }

    private var statusColor: Color {
        switch thread.status {
        case .running:
            return .blue
        case .paused:
            return .orange
        case .completed:
            return .green
        case .failed:
            return .red
        }
    }
}

/// Sheet wrapper for thread details
struct ThreadDetailSheet: View {
    let thread: ExecutionThread
    let executionService: WorkflowExecutionService
    let onRefresh: () async -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ThreadDetailContent(
                thread: thread,
                executionService: executionService,
                onRefresh: onRefresh
            )
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .frame(minWidth: 500, minHeight: 400)
    }
}

/// Detail view content for a single execution thread
struct ThreadDetailContent: View {
    let thread: ExecutionThread
    let executionService: WorkflowExecutionService
    let onRefresh: () async -> Void
    @State private var history: WorkflowExecutionPayload?
    @State private var run: WorkflowExecutionPayload?
    @State private var cacheStats: WorkflowExecutionPayload?
    @State private var diagramImage: NSImage?
    @State private var supplementalError: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Header
                HStack {
                    VStack(alignment: .leading) {
                        Text(thread.workflowName)
                            .font(.title)
                        Text("Thread: \(thread.threadId)")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }

                    Spacer()

                    statusBadge
                }
                .padding()

                Divider()

                // Details
                VStack(alignment: .leading, spacing: 12) {
                    DetailRow(label: "Workflow ID", value: thread.workflowId)

                    if let checkpointId = thread.checkpointId {
                        DetailRow(label: "Checkpoint ID", value: checkpointId)
                    }

                    if let error = thread.error {
                        DetailRow(label: "Error", value: error, isError: true)
                    }
                }
                .padding(.horizontal)

                Divider()

                if let supplementalError {
                    DetailRow(label: "Supplemental Data Error", value: supplementalError, isError: true)
                        .padding(.horizontal)
                }

                if let cacheStats {
                    PayloadSummary(label: "Workflow Cache", payload: cacheStats)
                        .padding(.horizontal)
                }

                if let run {
                    PayloadSummary(label: "Run", payload: run)
                        .padding(.horizontal)
                }

                if let history {
                    PayloadSummary(label: "History", payload: history)
                        .padding(.horizontal)
                }

                if let diagramImage {
                    Image(nsImage: diagramImage)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(maxHeight: 220)
                        .padding(.horizontal)
                }

                Spacer()
            }
        }
        .task(id: thread.threadId) {
            await loadSupplementalData()
        }
        .navigationTitle(thread.workflowName)
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                if thread.status == .paused {
                    Button {
                        Task {
                            _ = try? await executionService.resumeWorkflow(threadId: thread.threadId)
                            await onRefresh()
                        }
                    } label: {
                        Label("Resume", systemImage: "play.fill")
                    }
                }

                Button {
                    Task { await onRefresh() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }

                Button {
                    Task { await clearWorkflowCache() }
                } label: {
                    Label("Clear Cache", systemImage: "externaldrive.badge.xmark")
                }
            }
        }
    }

    private func loadSupplementalData() async {
        supplementalError = nil

        async let runTask = loadRun()
        async let historyTask = loadHistory()
        async let cacheTask = loadCacheStats()
        async let diagramTask = loadDiagram()

        await runTask
        await historyTask
        await cacheTask
        await diagramTask
    }

    private func loadRun() async {
        do {
            run = try await executionService.getWorkflowRun(threadId: thread.threadId)
        } catch {
            supplementalError = error.localizedDescription
        }
    }

    private func loadHistory() async {
        do {
            history = try await executionService.getThreadHistory(threadId: thread.threadId)
        } catch {
            supplementalError = error.localizedDescription
        }
    }

    private func loadCacheStats() async {
        do {
            cacheStats = try await executionService.getWorkflowCacheStats(workflowId: thread.workflowId)
        } catch {
            supplementalError = error.localizedDescription
        }
    }

    private func loadDiagram() async {
        do {
            let data = try await executionService.getThreadDiagramPNG(threadId: thread.threadId)
            diagramImage = NSImage(data: data)
        } catch {
            supplementalError = error.localizedDescription
        }
    }

    private func clearWorkflowCache() async {
        do {
            try await executionService.clearWorkflowCache(workflowId: thread.workflowId)
            cacheStats = nil
        } catch {
            supplementalError = error.localizedDescription
        }
    }

    @ViewBuilder
    private var statusBadge: some View {
        let (color, icon) = statusInfo

        HStack(spacing: 4) {
            Image(systemName: icon)
            Text(thread.status.rawValue.capitalized)
        }
        .font(.headline)
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(color.opacity(0.2))
        .foregroundColor(color)
        .cornerRadius(8)
    }

    private var statusInfo: (Color, String) {
        switch thread.status {
        case .running:
            return (.blue, "play.circle.fill")
        case .paused:
            return (.orange, "pause.circle.fill")
        case .completed:
            return (.green, "checkmark.circle.fill")
        case .failed:
            return (.red, "exclamationmark.circle.fill")
        }
    }
}

private struct PayloadSummary: View {
    let label: String
    let payload: WorkflowExecutionPayload

    var body: some View {
        DetailRow(
            label: label,
            value: "\(payload.values.count) field\(payload.values.count == 1 ? "" : "s")"
        )
    }
}

/// A simple key-value detail row
struct DetailRow: View {
    let label: String
    let value: String
    var isError: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundColor(.secondary)
            Text(value)
                .font(.body)
                .foregroundColor(isError ? .red : .primary)
        }
    }
}

#Preview {
    WorkflowExecutionView()
}
