import SwiftUI
import OSLog

let batchDetailLogger = Logger(subsystem: "ca.tubb.Fichero", category: "BatchDetailView")

struct BatchDetailView: View {
    let batch: BatchInfo
    @EnvironmentObject var apiClient: APIClient
    @ObservedObject var libraryManager: LibraryManager

    @State var refreshedBatch: BatchInfo?
    @State var isLoading = false
    @State var error: String?

    var displayBatch: BatchInfo {
        refreshedBatch ?? batch
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                headerSection

                Divider()

                progressSection

                Divider()

                configurationSection

                if let items = displayBatch.items, !items.isEmpty {
                    Divider()
                    itemsSection(items)
                }

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

    // MARK: - Error Section

    @ViewBuilder
    func errorSection(_ errorMessage: String) -> some View {
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

    var statusColor: Color {
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

    var batchStatus: Status {
        switch displayBatch.status {
        case "completed": return .completed
        case "running": return .processing
        case "pending": return .pending
        case "failed", "partial_failure": return .failed
        default: return .pending
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
