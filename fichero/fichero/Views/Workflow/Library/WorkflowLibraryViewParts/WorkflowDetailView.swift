import SwiftUI

/// Detail view for a selected workflow
struct WorkflowDetailView: View {
    let workflow: WorkflowSidebarItem
    let onEdit: () -> Void
    let onDelete: () -> Void
    let onDuplicate: () -> Void
    let onExecute: () -> Void
    let onExport: () -> Void

    @Environment(WorkflowStore.self) var workflowStore
    @ObservedObject var featureManager = FeatureManager.shared
    @State private var isExecuting = false
    @State private var executionStatus: String?
    @State private var executionError: String?
    @State private var currentThreadId: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                HStack {
                    Image(systemName: "flowchart")
                        .font(.system(size: 48))
                        .foregroundColor(.accentColor)

                    VStack(alignment: .leading) {
                        HStack(spacing: 8) {
                            Text(workflow.name)
                                .font(.largeTitle)
                                .fontWeight(.bold)
                            if workflow.isSystem {
                                Image(systemName: "lock.fill")
                                    .font(.title3)
                                    .foregroundColor(.secondary)
                            }
                        }

                        if let desc = workflow.description, !desc.isEmpty {
                            Text(desc)
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                    }

                    Spacer()
                }

                Divider()

                // Stats
                HStack(spacing: 32) {
                    StatView(title: "Nodes", value: "\(workflow.nodeCount)", icon: "square.on.circle")
                    StatView(title: "Connections", value: "\(workflow.edgeCount)", icon: "arrow.right")
                }

                Divider()

                // Execution section
                VStack(alignment: .leading, spacing: 12) {
                    Text("Execute")
                        .font(.headline)

                    HStack(spacing: 12) {
                        Button {
                            executeWorkflow()
                        } label: {
                            Label(isExecuting ? "Running..." : "Run Workflow", systemImage: "play.fill")
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.green)
                        .disabled(isExecuting || workflow.nodeCount == 0)
                    }

                    if let status = executionStatus {
                        HStack {
                            if isExecuting {
                                ProgressView()
                                    .scaleEffect(0.8)
                            } else {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundColor(.green)
                            }
                            Text(status)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding(8)
                        .background(Color(.controlBackgroundColor))
                        .cornerRadius(6)
                    }

                    if let error = executionError {
                        HStack {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundColor(.orange)
                            Text(error)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding(8)
                        .background(Color.orange.opacity(0.1))
                        .cornerRadius(6)
                    }
                }

                Divider()

                // Actions
                VStack(alignment: .leading, spacing: 12) {
                    Text("Actions")
                        .font(.headline)

                    HStack(spacing: 12) {
                        if !workflow.isSystem {
                            Button {
                                onEdit()
                            } label: {
                                Label("Edit Workflow", systemImage: "pencil")
                            }
                            .buttonStyle(.borderedProminent)
                        }

                        Button {
                            onDuplicate()
                        } label: {
                            Label("Duplicate", systemImage: "doc.on.doc")
                        }
                        .buttonStyle(.bordered)

                        if !workflow.isSystem, featureManager.isWorkflowImportExportEnabled {
                            Button {
                                onExport()
                            } label: {
                                Label("Export", systemImage: "square.and.arrow.up")
                            }
                            .buttonStyle(.bordered)
                        }

                        if !workflow.isSystem {
                            Button(role: .destructive) {
                                onDelete()
                            } label: {
                                Label("Delete", systemImage: "trash")
                            }
                            .buttonStyle(.bordered)
                        }
                    }
                }

                Spacer()
            }
            .padding(24)
        }
    }

    // MARK: - Actions

    private func executeWorkflow() {
        Task {
            isExecuting = true
            executionStatus = "Starting workflow..."
            executionError = nil

            do {
                let thread = try await workflowStore.executeWorkflow(workflow.id)
                currentThreadId = thread.threadId
                executionStatus = "Thread: \(thread.threadId) - \(thread.status.rawValue)"

                // Poll for completion
                await pollForCompletion(threadId: thread.threadId)
            } catch {
                executionError = error.localizedDescription
                executionStatus = nil
                isExecuting = false
            }
        }
    }

    private func pollForCompletion(threadId: String) async {
        // Poll every 2 seconds for status updates
        while isExecuting {
            do {
                try await Task.sleep(nanoseconds: 2_000_000_000)
                guard !Task.isCancelled else { break }

                let status = try await workflowStore.getExecutionStatus(threadId)
                executionStatus = "Thread: \(status.threadId) - \(status.status.rawValue)"

                switch status.status {
                case .completed:
                    isExecuting = false
                    executionStatus = "Completed successfully"
                case .error, .failed:
                    isExecuting = false
                    executionError = status.error ?? "Workflow failed"
                    executionStatus = nil
                case .cancelled, .stopped, .deleted:
                    isExecuting = false
                    executionError = status.error ?? "Workflow \(status.status.rawValue)"
                    executionStatus = nil
                case .paused:
                    executionStatus = "Paused - waiting for input"
                case .running:
                    // Continue polling
                    break
                }
            } catch {
                // Stop polling on error
                isExecuting = false
                executionError = "Failed to check status: \(error.localizedDescription)"
            }
        }
    }
}

/// Simple stat display view
struct StatView: View {
    let title: String
    let value: String
    let icon: String

    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundColor(.secondary)
            Text(value)
                .font(.title)
                .fontWeight(.bold)
            Text(title)
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}
