import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowExecutionView")

/// View for monitoring workflow execution threads
struct WorkflowExecutionView: View {
    @StateObject private var executionService = WorkflowExecutionService()
    @State private var selectedThread: ExecutionThread?
    @State private var isLoading = false

    var body: some View {
        NavigationSplitView {
            threadList
        } detail: {
            if let thread = selectedThread {
                ThreadDetailView(
                    thread: thread,
                    executionService: executionService,
                    onRefresh: { await refreshThread(thread.threadId) }
                )
            } else {
                ContentUnavailableView(
                    "No Thread Selected",
                    systemImage: "arrow.triangle.2.circlepath",
                    description: Text("Select a thread to view its details")
                )
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadThreads()
        }
        .refreshable {
            await loadThreads()
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
                List(executionService.threads, selection: $selectedThread) { thread in
                    ThreadRow(thread: thread)
                        .tag(thread)
                        .contextMenu {
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
        .navigationTitle("Execution Threads")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task { await loadThreads() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(isLoading)
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

/// Detail view for a single execution thread
struct ThreadDetailView: View {
    let thread: ExecutionThread
    let executionService: WorkflowExecutionService
    let onRefresh: () async -> Void

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

                Spacer()
            }
        }
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
            }
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
