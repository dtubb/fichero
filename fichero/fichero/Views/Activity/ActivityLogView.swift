import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ActivityLogView")

// Shows the saved execution log for a workflow run
struct ActivityLogView: View {
    let selectedRun: SelectedActivityRun
    @Environment(APIClient.self) var apiClient
    @Environment(WorkflowExecutionObserver.self) private var executionObserver

    /// Shared live-execution store keyed by threadId (#2546). Optional so the
    /// view never crashes where the store isn't injected (e.g. previews).
    @Environment(WorkflowExecutionStore.self) private var executionStore: WorkflowExecutionStore?

    @State private var workflowRun: WorkflowRunResponse?
    @State private var isLoading = false
    @State private var error: String?

    /// Live/completed execution for the selected run.
    ///
    /// Prefers the threadId-keyed `WorkflowExecutionStore` (#2546) so the live
    /// log streams for a run started ANYWHERE — Activity's subscribe-on-select
    /// owns the SSE — not only runs the in-process editor fed into the
    /// workflowId-keyed `WorkflowExecutionObserver`. Without this the Live Log
    /// tab read an empty observer and sat at "Waiting for log output…" while the
    /// store was already accumulating `logLines` (#2546 follow-up).
    private var liveExecution: WorkflowExecution? {
        if let threadId = selectedRun.threadId,
           let stored = executionStore?.execution(forThreadId: threadId) {
            return stored
        }
        guard let workflowId = selectedRun.workflowId else { return nil }
        return executionObserver.getExecution(for: workflowId)
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header with copy button
            HStack {
                Text("Execution Log")
                    .font(.headline)

                if selectedRun.isLive {
                    Text("(Live)")
                        .font(.caption)
                        .foregroundStyle(.blue)
                }

                Spacer()

                if let log = workflowRun?.executionLog, !log.isEmpty {
                    Button {
                        PlatformPasteboard.writeString(log)
                    } label: {
                        Label("Copy", systemImage: "doc.on.doc")
                    }
                    .buttonStyle(.borderless)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(.bar)

            Divider()

            // Content - handle live vs completed runs differently
            if selectedRun.isLive {
                liveLogContent
            } else if isLoading {
                ProgressView("Loading...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = error {
                errorView(error)
            } else if let run = workflowRun {
                if let log = run.executionLog, !log.isEmpty {
                    executionLogContent(log, run: run)
                } else {
                    noDataView
                }
            } else {
                emptyView
            }
        }
        .task(id: selectedRun.threadId.map { $0 + (selectedRun.isLive ? ":live" : ":done") }) {
            guard !Task.isCancelled else { return }
            if !selectedRun.isLive {
                await loadWorkflowRun()
            }
        }
    }
}

// MARK: - Log Content

extension ActivityLogView {
    @ViewBuilder
    private var liveLogContent: some View {
        VStack(spacing: 0) {
            // Running status header
            HStack {
                ProgressView()
                    .scaleEffect(0.7)
                Text("Live Log")
                    .font(.subheadline.bold())
                Spacer()
                if let execution = liveExecution {
                    Text("\(execution.logLines.count) lines")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(10)
            .background(.blue.opacity(0.1))

            Divider()

            // Streamed log lines
            if let execution = liveExecution, !execution.logLines.isEmpty {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 2) {
                            ForEach(Array(execution.logLines.enumerated()), id: \.offset) { index, line in
                                logLineView(line)
                                    .id(index)
                            }
                        }
                        .padding(8)
                    }
                    .onChange(of: execution.logLines.count) { _, newCount in
                        // Auto-scroll to bottom
                        withAnimation(.easeOut(duration: 0.2)) {
                            proxy.scrollTo(newCount - 1, anchor: .bottom)
                        }
                    }
                }
                .background(Color(platformColor: .textBackgroundColor))
            } else {
                VStack(spacing: 12) {
                    Spacer()
                    ProgressView()
                    Text("Waiting for log output...")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color(platformColor: .textBackgroundColor))
            }
        }
    }

    @ViewBuilder
    private func logLineView(_ line: String) -> some View {
        // Parse timestamp and message for nice formatting
        // Format: [HH:MM:SS.mmm] message
        let parts = line.split(separator: "]", maxSplits: 1)
        if parts.count == 2 {
            let timestamp = String(parts[0]).trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
            let message = activityHumanizeMessage(String(parts[1]).trimmingCharacters(in: .whitespaces))

            HStack(alignment: .top, spacing: 8) {
                Text(timestamp)
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .frame(width: 80, alignment: .leading)

                Text(message)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(messageColor(for: message))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
        } else {
            Text(activityHumanizeMessage(line))
                    .font(.system(.caption, design: .monospaced))
                .padding(.horizontal, 8)
                .padding(.vertical, 2)
        }
    }

    private func messageColor(for message: String) -> Color {
        if message.contains("ERROR") || message.contains("FAILED") {
            return .red
        } else if message.contains("completed") || message.contains("successfully") {
            return .green
        } else if message.contains("started") || message.contains("Starting") {
            return .blue
        } else {
            return .primary
        }
    }

    @ViewBuilder
    // swiftlint:disable:next function_body_length
    private func executionLogContent(_ log: String, run: WorkflowRunResponse) -> some View {
        VStack(spacing: 0) {
            // Status header
            if run.status == "failed" || run.error != nil {
                HStack {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.red)
                    Text("Workflow Failed")
                        .font(.subheadline.bold())
                    Spacer()
                    if let duration = run.durationMs {
                        Text(ActivityViewHelpers.formatDuration(duration))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(10)
                .background(.red.opacity(0.1))

                if let error = run.error {
                    Text(error)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(.red)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                        .background(.red.opacity(0.05))
                }

                Divider()
            } else if run.status == "completed" {
                HStack {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                    Text("Workflow Completed")
                        .font(.subheadline.bold())
                    Spacer()
                    if let duration = run.durationMs {
                        Text(ActivityViewHelpers.formatDuration(duration))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(10)
                .background(.green.opacity(0.1))

                Divider()
            }

            // Log content
            ScrollView {
                Text(log)
                    .font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding()
            }
            .background(Color(platformColor: .textBackgroundColor))
        }
    }

    @ViewBuilder
    private func errorView(_ error: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle)
                .foregroundStyle(.orange)
            Text("Failed to load execution log")
                .font(.headline)
            Text(error)
                .font(.caption)
                .foregroundStyle(.secondary)
            Button("Retry") {
                Task { await loadWorkflowRun() }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private var noDataView: some View {
        VStack(spacing: 12) {
            Image(systemName: "doc.text")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text("No execution log available")
                .font(.headline)
            Text("The workflow may not have been run yet.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private var emptyView: some View {
        VStack(spacing: 12) {
            Image(systemName: "doc.text")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text("No data available")
                .foregroundStyle(.secondary)
            if selectedRun.threadId != nil {
                Button("Load Data") {
                    Task { await loadWorkflowRun() }
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func loadWorkflowRun() async {
        guard let threadId = selectedRun.threadId else {
            error = "No thread ID available"
            return
        }
        isLoading = true
        error = nil
        do {
            let activityService = ActivityService(apiClient: apiClient)
            workflowRun = try await activityService.getWorkflowRun(threadId: threadId)
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}

// MARK: - Preview

#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    let selectedRun = SelectedActivityRun(
        id: "test-run",
        name: "Test Workflow",
        workflowId: "workflow-123",
        threadId: "thread-456",
        timestamp: Date(),
        status: .completed,
        isLive: false,
        childType: nil
    )

    ActivityLogView(selectedRun: selectedRun)
        .environment(library.apiClient)
        .frame(width: 800, height: 600)
}
