import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowExecutionView")

/// View for monitoring workflow execution threads
struct WorkflowExecutionView: View {
    @Environment(WorkflowStore.self) private var workflowStore
    @State private var threads: [ExecutionThread] = []
    @State private var selectedThread: ExecutionThread?
    @State private var isLoading = false

    var body: some View {
        threadList
            .task {
                guard !Task.isCancelled else { return }
                await loadThreads()
            }
            .refreshable {
                await loadThreads()
            }
            .sheet(item: $selectedThread) { thread in
                ThreadDetailSheet(
                    thread: thread,
                    onRefresh: {
                        await refreshThread(thread.threadId)
                        await loadThreads()
                    }
                )
            }
    }

    @ViewBuilder
    private var threadList: some View {
        Group {
            if isLoading && threads.isEmpty {
                ProgressView("Loading threads...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if threads.isEmpty {
                ContentUnavailableView(
                    "No Execution Threads",
                    systemImage: "play.circle",
                    description: Text("Run a workflow to see execution threads here")
                )
            } else {
                List(threads) { thread in
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
        }
    }

    private func loadThreads() async {
        isLoading = true
        defer { isLoading = false }

        do {
            threads = try await workflowStore.listExecutionThreads()
        } catch {
            logger.error("Failed to load threads: \(String(describing: error))")
        }
    }

    private func refreshThread(_ threadId: String) async {
        do {
            let updated = try await workflowStore.getExecutionStatus(threadId)
            selectedThread = updated
        } catch {
            logger.error("Failed to refresh thread: \(String(describing: error))")
        }
    }

    private func resumeThread(_ threadId: String) async {
        do {
            let updated = try await workflowStore.resumeExecution(threadId)
            selectedThread = updated
            await loadThreads()
        } catch {
            logger.error("Failed to resume thread: \(String(describing: error))")
        }
    }

    private func deleteThread(_ threadId: String) async {
        do {
            try await workflowStore.deleteExecutionThread(threadId)
            if selectedThread?.threadId == threadId {
                selectedThread = nil
            }
            await loadThreads()
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
        case .error, .failed:
            return "exclamationmark.circle.fill"
        case .cancelled, .stopped, .deleted:
            return "stop.circle.fill"
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
        case .error, .failed:
            return .red
        case .cancelled, .stopped, .deleted:
            return .orange
        }
    }
}

/// Sheet wrapper for thread details
struct ThreadDetailSheet: View {
    let thread: ExecutionThread
    let onRefresh: () async -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ThreadDetailContent(
                thread: thread,
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
    let onRefresh: () async -> Void
    @Environment(WorkflowStore.self) private var workflowStore

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
        .navigationTitle(thread.workflowName)
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                if thread.status == .paused {
                    Button {
                        Task {
                            _ = try? await workflowStore.resumeExecution(thread.threadId)
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
        case .error, .failed:
            return (.red, "exclamationmark.circle.fill")
        case .cancelled, .stopped, .deleted:
            return (.orange, "stop.circle.fill")
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
    let library = LibraryManager.shared.globalLibrary!
    WorkflowExecutionView()
        .environment(library.workflowStore)
}
