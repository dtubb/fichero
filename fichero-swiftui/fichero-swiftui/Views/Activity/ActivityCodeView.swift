import OSLog
import SwiftUI

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "ActivityCodeView")

/// Shows the saved Python code for a workflow run
struct ActivityCodeView: View {
    let selectedRun: SelectedActivityRun
    @EnvironmentObject var apiClient: APIClient

    @State private var workflowRun: WorkflowRunResponse?
    @State private var isLoading = false
    @State private var error: String?

    var body: some View {
        VStack(spacing: 0) {
            // Header with copy button
            HStack {
                Text("LangGraph Code")
                    .font(.headline)
                Spacer()
                if let code = workflowRun?.pythonCode, !code.isEmpty {
                    Button {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(code, forType: .string)
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

            // Content
            if isLoading {
                ProgressView("Loading...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = error {
                errorView(error)
            } else if let run = workflowRun {
                if let code = run.pythonCode, !code.isEmpty {
                    codeContent(code)
                } else {
                    noDataView
                }
            } else {
                emptyView
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadWorkflowRun()
        }
        .onChange(of: selectedRun.threadId) { _, _ in
            Task {
                await loadWorkflowRun()
            }
        }
    }

    @ViewBuilder
    private func codeContent(_ code: String) -> some View {
        ScrollView {
            Text(code)
                .font(.system(.caption, design: .monospaced))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
        }
        .background(Color(nsColor: .textBackgroundColor))
    }

    @ViewBuilder
    private func errorView(_ error: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle)
                .foregroundStyle(.orange)
            Text("Failed to load code")
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
            Image(systemName: "chevron.left.forwardslash.chevron.right")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text("No code available")
                .font(.headline)
            Text("The workflow code may not have been generated.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private var emptyView: some View {
        VStack(spacing: 12) {
            Image(systemName: "chevron.left.forwardslash.chevron.right")
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
            let activityService = ActivityServiceGenerated(apiClient: apiClient)
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

    ActivityCodeView(selectedRun: selectedRun)
        .environmentObject(library.apiClient)
        .frame(width: 600, height: 500)
}
