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

                // Quick stats — only show live progress card when data is present or run is active.
                // A completed 0-file run has no progress data, so fall through to historicalStatsCard
                // to avoid showing "Starting…" for an already-finished workflow.
                if let execution = liveExecution,
                   execution.isRunning || !execution.documentProgress.isEmpty || execution.overallProgress != nil {
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
                docStepGrid(execution)
            }
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    @ViewBuilder
    // swiftlint:disable:next function_body_length
    private func docStepGrid(_ execution: WorkflowExecution) -> some View {
        let docs = execution.orderedDocumentProgress
        let stepNames = Array(Set(docs.flatMap { Array($0.stepStatuses.keys) })).sorted()

        VStack(alignment: .leading, spacing: 6) {
            Text("Files × Steps")
                .font(.subheadline.bold())
                .foregroundStyle(.secondary)

            if stepNames.isEmpty {
                Text("No step data yet")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    VStack(alignment: .leading, spacing: 0) {
                        // Header row
                        HStack(spacing: 0) {
                            Text("Document")
                                .font(.caption2.bold())
                                .foregroundStyle(.secondary)
                                .frame(width: 140, alignment: .leading)
                            ForEach(stepNames, id: \.self) { step in
                                Text(step)
                                    .font(.caption2.bold())
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                                    .frame(width: 44)
                            }
                        }
                        .padding(.bottom, 4)

                        Divider()

                        // Document rows
                        ForEach(docs.prefix(20)) { doc in
                            HStack(spacing: 0) {
                                Text(doc.documentName)
                                    .font(.caption)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                                    .frame(width: 140, alignment: .leading)
                                ForEach(stepNames, id: \.self) { step in
                                    stepCell(doc.stepStatuses[step])
                                        .frame(width: 44)
                                }
                            }
                            .padding(.vertical, 2)
                        }

                        if docs.count > 20 {
                            Text("+ \(docs.count - 20) more")
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                                .padding(.top, 4)
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func stepCell(_ status: StepStatus?) -> some View {
        switch status {
        case .none, .pending:
            Image(systemName: "circle")
                .foregroundStyle(.tertiary)
                .font(.caption)
        case .running:
            ProgressView()
                .scaleEffect(0.5)
                .frame(width: 16, height: 16)
        case .completed(_, let cached):
            Image(systemName: cached ? "bolt.circle.fill" : "checkmark.circle.fill")
                .foregroundStyle(cached ? .blue : .green)
                .font(.caption)
        case .failed:
            Image(systemName: "xmark.circle.fill")
                .foregroundStyle(.red)
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

    let mockExecution = WorkflowExecution(
        id: "wf-preview",
        name: "Transcribe",
        threadId: "th-preview",
        startTime: Date().addingTimeInterval(-90),
        status: .running,
        nodeStates: [:],
        documentProgress: [
            "letter_001.pdf": DocumentProgress(
                id: "letter_001.pdf",
                documentName: "letter_001.pdf",
                stepStatuses: [
                    "transcribe": .completed(duration: 2300, cached: false),
                    "extract": .running,
                    "catalogue": .pending
                ]
            ),
            "letter_002.pdf": DocumentProgress(
                id: "letter_002.pdf",
                documentName: "letter_002.pdf",
                stepStatuses: [
                    "transcribe": .completed(duration: 1800, cached: true),
                    "extract": .pending,
                    "catalogue": .pending
                ]
            ),
            "letter_003.pdf": DocumentProgress(
                id: "letter_003.pdf",
                documentName: "letter_003.pdf",
                stepStatuses: [
                    "transcribe": .failed(error: "timeout"),
                    "extract": .pending,
                    "catalogue": .pending
                ]
            )
        ],
        currentFilePath: "letter_001.pdf",
        currentNodeId: "extract",
        currentNodeName: "Extract",
        isRunning: true,
        workflowError: nil,
        totalFiles: 3,
        processedFiles: 0
    )

    ActivityOverviewView(
        selectedRun: selectedRun,
        activityItems: mockItems,
        liveExecution: mockExecution,
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
