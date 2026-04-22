import SwiftUI

/// Overview view showing summary of workflow run
struct ActivityOverviewView: View {
    let selectedRun: SelectedActivityRun
    let activityItems: [ActivityItem]
    let liveExecution: WorkflowExecution?
    let errorCount: Int

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                // Status card
                statusCard

                // Quick stats
                if let execution = liveExecution {
                    liveStatsCard(execution)
                } else {
                    historicalStatsCard
                }

                // Recent activity
                if !activityItems.isEmpty {
                    recentActivityCard
                }
            }
            .padding()
        }
    }

    @ViewBuilder
    private var statusCard: some View {
        VStack(spacing: 8) {
            Image(systemName: statusIcon)
                .font(.system(size: 40))
                .foregroundStyle(statusColor)

            Text(statusText)
                .font(.headline)

            Text(selectedRun.timestamp, format: .dateTime)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    @ViewBuilder
    private func liveStatsCard(_ execution: WorkflowExecution) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Progress")
                .font(.headline)

            if let progress = execution.overallProgress {
                ProgressView(value: progress)
                    .scaleEffect(y: 1.5)

                HStack {
                    Text("\(Int(progress * 100))%")
                        .font(.title2.monospacedDigit())

                    Spacer()

                    if execution.totalFiles > 0 {
                        Text("\(execution.processedFiles) of \(execution.totalFiles) files")
                            .foregroundStyle(.secondary)
                    }
                }
            } else if !execution.documentProgress.isEmpty {
                Text("\(execution.processedFiles) files processed")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                HStack(spacing: 8) {
                    ProgressView().scaleEffect(0.7)
                    Text("Starting…")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }

            if let currentFile = execution.currentFileName {
                HStack {
                    Text("Current:")
                        .foregroundStyle(.secondary)
                    Text(currentFile)
                        .lineLimit(1)
                }
                .font(.caption)
            }

            if !execution.documentProgress.isEmpty {
                Divider()

                Text("Files")
                    .font(.subheadline.bold())
                    .foregroundStyle(.secondary)

                ForEach(execution.orderedDocumentProgress.prefix(8)) { doc in
                    HStack(spacing: 6) {
                        docStatusIcon(doc)
                        Text(doc.documentName)
                            .font(.caption)
                            .lineLimit(1)
                        Spacer()
                    }
                }

                if execution.documentProgress.count > 8 {
                    Text("+ \(execution.documentProgress.count - 8) more")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    @ViewBuilder
    private func docStatusIcon(_ doc: DocumentProgress) -> some View {
        let hasFailed = doc.stepStatuses.values.contains {
            if case .failed = $0 { return true }
            return false
        }
        let isRunning = doc.stepStatuses.values.contains {
            if case .running = $0 { return true }
            return false
        }
        if hasFailed {
            Image(systemName: "xmark.circle.fill")
                .foregroundStyle(.red)
                .font(.caption)
        } else if isRunning {
            ProgressView()
                .scaleEffect(0.5)
                .frame(width: 12, height: 12)
        } else if !doc.stepStatuses.isEmpty {
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(.green)
                .font(.caption)
        } else {
            Image(systemName: "circle")
                .foregroundStyle(.secondary)
                .font(.caption)
        }
    }

    @ViewBuilder
    private var historicalStatsCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Summary")
                .font(.headline)

            HStack(spacing: 20) {
                statItem(title: "Events", value: "\(activityItems.count)")
                statItem(title: "Errors", value: "\(errorCount)", color: errorCount > 0 ? .red : nil)
            }
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    @ViewBuilder
    private func statItem(title: String, value: String, color: Color? = nil) -> some View {
        VStack {
            Text(value)
                .font(.title2.monospacedDigit())
                .foregroundStyle(color ?? .primary)
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private var recentActivityCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Recent Activity")
                .font(.headline)

            ForEach(activityItems.prefix(5)) { item in
                HStack(spacing: 8) {
                    Image(systemName: item.typeIcon)
                        .foregroundStyle(ActivityViewHelpers.levelColor(item.level))
                        .frame(width: 16)

                    Text(item.message)
                        .font(.caption)
                        .lineLimit(1)

                    Spacer()

                    if let date = item.parsedTimestamp {
                        Text(date, style: .time)
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }
            }
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    private var statusIcon: String {
        ActivityViewHelpers.statusIcon(for: selectedRun.status)
    }

    private var statusColor: Color {
        ActivityViewHelpers.statusColor(for: selectedRun.status)
    }

    private var statusText: String {
        ActivityViewHelpers.statusText(for: selectedRun.status)
    }
}

// MARK: - Preview

#Preview("Running") {
    let selectedRun = SelectedActivityRun(
        id: "test-run",
        name: "Test Workflow",
        workflowId: "workflow-123",
        threadId: "thread-456",
        timestamp: Date(),
        status: .running,
        isLive: true,
        childType: nil
    )

    let mockItems = [
        ActivityItem(
            id: "item-1",
            type: "log",
            level: "info",
            timestamp: "2024-01-15 10:30:00",
            message: "Starting workflow execution",
            workflowId: nil,
            batchId: nil,
            threadId: nil,
            nodeId: nil,
            metadataRaw: nil,
            durationMs: nil,
            error: nil
        ),
        ActivityItem(
            id: "item-2",
            type: "log",
            level: "info",
            timestamp: "2024-01-15 10:30:05",
            message: "Processing document 1 of 10",
            workflowId: nil,
            batchId: nil,
            threadId: nil,
            nodeId: nil,
            metadataRaw: nil,
            durationMs: nil,
            error: nil
        )
    ]

    ActivityOverviewView(
        selectedRun: selectedRun,
        activityItems: mockItems,
        liveExecution: nil,
        errorCount: 0
    )
    .frame(width: 600, height: 500)
}

#Preview("With Errors") {
    let selectedRun = SelectedActivityRun(
        id: "test-run",
        name: "Test Workflow",
        workflowId: "workflow-123",
        threadId: "thread-456",
        timestamp: Date(),
        status: .failed,
        isLive: false,
        childType: nil
    )

    let mockItems = [
        ActivityItem(
            id: "item-1",
            type: "log",
            level: "error",
            timestamp: "2024-01-15 10:30:00",
            message: "Failed to process document.pdf",
            workflowId: nil,
            batchId: nil,
            threadId: nil,
            nodeId: nil,
            metadataRaw: nil,
            durationMs: nil,
            error: nil
        )
    ]

    ActivityOverviewView(
        selectedRun: selectedRun,
        activityItems: mockItems,
        liveExecution: nil,
        errorCount: 3
    )
    .frame(width: 600, height: 500)
}
