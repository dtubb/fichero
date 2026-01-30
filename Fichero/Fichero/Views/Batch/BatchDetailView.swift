import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "BatchDetailView")

/// Detail view for a batch showing configuration, progress, and item details
struct BatchDetailView: View {
    let batch: BatchInfo
    @EnvironmentObject var apiClient: APIClient
    @ObservedObject var libraryManager: LibraryManager

    @State private var refreshedBatch: BatchInfo?
    @State private var isLoading = false
    @State private var error: String?

    private var displayBatch: BatchInfo {
        refreshedBatch ?? batch
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                headerSection

                Divider()

                // Progress
                progressSection

                Divider()

                // Configuration
                configurationSection

                // Items (if available)
                if let items = displayBatch.items, !items.isEmpty {
                    Divider()
                    itemsSection(items)
                }

                // Error (if any)
                if let errorMessage = displayBatch.errorMessage {
                    Divider()
                    errorSection(errorMessage)
                }
            }
            .padding()
        }
        .task {
            guard !Task.isCancelled else { return }
            await refreshBatch()
        }
    }

    // MARK: - Header Section

    @ViewBuilder
    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: displayBatch.statusIcon)
                    .font(.largeTitle)
                    .foregroundStyle(statusColor)

                VStack(alignment: .leading, spacing: 4) {
                    Text("Batch \(String(displayBatch.batchId.prefix(8)))")
                        .font(.title2.bold())
                        .monospaced()

                    HStack(spacing: 8) {
                        StatusBadge(status: batchStatus)

                        Text("Workflow: \(displayBatch.workflowId)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Spacer()

                // Action buttons
                actionButtons
            }
        }
    }

    @ViewBuilder
    private var actionButtons: some View {
        HStack(spacing: 8) {
            if displayBatch.status == "running" || displayBatch.status == "pending" {
                Button {
                    Task { await pauseBatch() }
                } label: {
                    Label("Pause", systemImage: "pause.fill")
                }
                .buttonStyle(.bordered)

                Button {
                    Task { await cancelBatch() }
                } label: {
                    Label("Cancel", systemImage: "stop.fill")
                }
                .buttonStyle(.bordered)
                .tint(.red)
            } else if displayBatch.status == "paused" {
                Button {
                    Task { await resumeBatch() }
                } label: {
                    Label("Resume", systemImage: "play.fill")
                }
                .buttonStyle(.borderedProminent)
            } else if displayBatch.status == "partial_failure" || displayBatch.failedItems > 0 {
                Button {
                    Task { await retryBatch() }
                } label: {
                    Label("Retry Failed", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.borderedProminent)
            }

            Button {
                Task { await refreshBatch() }
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .buttonStyle(.bordered)
            .disabled(isLoading)
        }
    }

    // MARK: - Progress Section

    @ViewBuilder
    private var progressSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Progress")
                .font(.headline)

            // Progress bar
            VStack(alignment: .leading, spacing: 8) {
                ProgressView(value: displayBatch.progressPercent, total: 100)
                    .progressViewStyle(.linear)
                    .scaleEffect(y: 2, anchor: .center)

                HStack {
                    Text("\(displayBatch.completedItems) completed")
                        .foregroundStyle(.green)

                    if displayBatch.failedItems > 0 {
                        Text("/ \(displayBatch.failedItems) failed")
                            .foregroundStyle(.red)
                    }

                    Text("/ \(displayBatch.totalItems) total")
                        .foregroundStyle(.secondary)

                    Spacer()

                    Text(String(format: "%.1f%%", displayBatch.progressPercent))
                        .font(.headline)
                        .fontWeight(.bold)
                }
                .font(.subheadline)
            }

            // Stats grid
            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 12) {
                statCard("Total", "\(displayBatch.totalItems)", .blue)
                statCard("Completed", "\(displayBatch.completedItems)", .green)
                statCard("Failed", "\(displayBatch.failedItems)", .red)
                statCard("Pending", "\(displayBatch.totalItems - displayBatch.completedItems - displayBatch.failedItems)", .gray)
            }
        }
    }

    @ViewBuilder
    private func statCard(_ title: String, _ value: String, _ color: Color) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.title2)
                .fontWeight(.bold)
                .foregroundStyle(color)
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(12)
        .background(color.opacity(0.1))
        .cornerRadius(8)
    }

    // MARK: - Configuration Section

    @ViewBuilder
    private var configurationSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Configuration")
                .font(.headline)

            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible())
            ], alignment: .leading, spacing: 12) {
                configField("Batch ID", displayBatch.batchId)
                configField("Workflow", displayBatch.workflowId)
                configField("Max Concurrent", "\(displayBatch.maxConcurrent)")
                configField("Created", displayBatch.createdAt)

                if let startedAt = displayBatch.startedAt {
                    configField("Started", startedAt)
                }

                if let completedAt = displayBatch.completedAt {
                    configField("Completed", completedAt)
                }
            }
        }
    }

    @ViewBuilder
    private func configField(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.body)
                .textSelection(.enabled)
        }
    }

    // MARK: - Items Section

    @ViewBuilder
    private func itemsSection(_ items: [BatchItemInfo]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Items")
                    .font(.headline)

                Spacer()

                Text("\(items.count) items")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            ForEach(items) { item in
                itemRow(item)
            }
        }
    }

    @ViewBuilder
    private func itemRow(_ item: BatchItemInfo) -> some View {
        HStack(spacing: 12) {
            // Status indicator
            Circle()
                .fill(itemStatusColor(item.status))
                .frame(width: 10, height: 10)

            // Item info
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("#\(item.itemIndex)")
                        .font(.subheadline)
                        .fontWeight(.medium)

                    Text(item.status.capitalized)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if let inputs = item.inputs, !inputs.isEmpty {
                    Text(inputs.map { "\($0.key): \($0.value)" }.joined(separator: ", "))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                if let error = item.error {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .lineLimit(2)
                }
            }

            Spacer()

            // Timing
            VStack(alignment: .trailing, spacing: 2) {
                if let started = item.startedAt {
                    Text(started)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if let completed = item.completedAt {
                    Text(completed)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(10)
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(8)
    }

    // MARK: - Error Section

    @ViewBuilder
    private func errorSection(_ errorMessage: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(.red)
                Text("Error")
                    .font(.headline)
            }

            Text(errorMessage)
                .font(.body)
                .foregroundStyle(.red)
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.red.opacity(0.1))
                .cornerRadius(8)
        }
    }

    // MARK: - Helpers

    private var statusColor: Color {
        switch displayBatch.status {
        case "pending": return .gray
        case "running": return .blue
        case "paused": return .yellow
        case "completed": return .green
        case "partial_failure": return .orange
        case "failed": return .red
        case "cancelled": return .gray
        default: return .secondary
        }
    }

    private var batchStatus: Status {
        switch displayBatch.status {
        case "completed": return .completed
        case "running": return .processing
        case "pending": return .pending
        case "failed", "partial_failure": return .failed
        default: return .pending
        }
    }

    private func itemStatusColor(_ status: String) -> Color {
        switch status {
        case "completed": return .green
        case "running": return .blue
        case "pending": return .gray
        case "failed": return .red
        default: return .secondary
        }
    }

    // MARK: - Actions

    private func refreshBatch() async {
        guard let library = libraryManager.openLibraries.first else { return }

        isLoading = true
        defer { isLoading = false }

        do {
            refreshedBatch = try await library.batchService.getBatchAsInfo(
                batchId: batch.batchId,
                includeItems: true
            )
        } catch {
            logger.error("Failed to refresh batch: \(error.localizedDescription)")
            self.error = error.localizedDescription
        }
    }

    private func pauseBatch() async {
        guard let library = libraryManager.openLibraries.first else { return }

        do {
            refreshedBatch = try await library.batchService.pauseBatchAsInfo(batchId: batch.batchId)
        } catch {
            logger.error("Failed to pause batch: \(error.localizedDescription)")
        }
    }

    private func resumeBatch() async {
        guard let library = libraryManager.openLibraries.first else { return }

        do {
            try await library.batchService.resumeBatch(batchId: batch.batchId)
            await refreshBatch()
        } catch {
            logger.error("Failed to resume batch: \(error.localizedDescription)")
        }
    }

    private func cancelBatch() async {
        guard let library = libraryManager.openLibraries.first else { return }

        do {
            refreshedBatch = try await library.batchService.cancelBatchAsInfo(batchId: batch.batchId)
        } catch {
            logger.error("Failed to cancel batch: \(error.localizedDescription)")
        }
    }

    private func retryBatch() async {
        guard let library = libraryManager.openLibraries.first else { return }

        do {
            try await library.batchService.retryBatch(batchId: batch.batchId)
            await refreshBatch()
        } catch {
            logger.error("Failed to retry batch: \(error.localizedDescription)")
        }
    }
}

#Preview {
    BatchDetailView(
        batch: BatchInfo(
            batchId: "batch-123456789",
            workflowId: "workflow-1",
            status: "running",
            totalItems: 100,
            completedItems: 42,
            failedItems: 3,
            maxConcurrent: 5,
            createdAt: "2024-01-25T10:00:00Z",
            startedAt: "2024-01-25T10:00:05Z",
            completedAt: nil,
            errorMessage: nil,
            items: [
                BatchItemInfo(
                    threadId: "thread-1",
                    itemIndex: 0,
                    inputs: ["file": "/path/to/file.pdf"],
                    status: "completed",
                    error: nil,
                    startedAt: "2024-01-25T10:00:05Z",
                    completedAt: "2024-01-25T10:00:15Z"
                ),
                BatchItemInfo(
                    threadId: "thread-2",
                    itemIndex: 1,
                    inputs: ["file": "/path/to/another.pdf"],
                    status: "running",
                    error: nil,
                    startedAt: "2024-01-25T10:00:10Z",
                    completedAt: nil
                ),
                BatchItemInfo(
                    threadId: "thread-3",
                    itemIndex: 2,
                    inputs: ["file": "/path/to/bad.pdf"],
                    status: "failed",
                    error: "File not found",
                    startedAt: "2024-01-25T10:00:12Z",
                    completedAt: "2024-01-25T10:00:13Z"
                )
            ]
        ),
        libraryManager: .shared
    )
    .environmentObject(APIClient())
    .frame(width: 700, height: 600)
}
