import OSLog
import SwiftUI

private let logger = Logger(subsystem: "com.fichero.fichero", category: "ActivityDiagramView")

/// Shows the workflow diagram visualization
struct ActivityDiagramView: View {
    let selectedRun: SelectedActivityRun
    @EnvironmentObject var apiClient: APIClient

    @State private var diagramImage: NSImage?
    @State private var isLoading = false
    @State private var error: String?

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Workflow Diagram")
                    .font(.headline)
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(.bar)

            Divider()

            // Content
            if isLoading {
                ProgressView("Loading diagram...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = error {
                errorView(error)
            } else if let image = diagramImage {
                diagramContent(image)
            } else {
                emptyView
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadDiagram()
        }
        .onChange(of: selectedRun.threadId) { _, _ in
            Task {
                await loadDiagram()
            }
        }
    }

    @ViewBuilder
    private func diagramContent(_ image: NSImage) -> some View {
        ScrollView([.horizontal, .vertical]) {
            Image(nsImage: image)
                .resizable()
                .aspectRatio(contentMode: .fit)
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
            Text("Failed to load diagram")
                .font(.headline)
            Text(error)
                .font(.caption)
                .foregroundStyle(.secondary)
            Button("Retry") {
                Task { await loadDiagram() }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private var emptyView: some View {
        VStack(spacing: 12) {
            Image(systemName: "flowchart")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text("No diagram available")
                .font(.headline)
            if selectedRun.threadId != nil {
                Button("Load Diagram") {
                    Task { await loadDiagram() }
                }
            } else {
                Text("Thread ID not available")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func loadDiagram() async {
        guard let threadId = selectedRun.threadId else {
            error = "No thread ID available"
            return
        }

        isLoading = true
        error = nil

        do {
            // Use thread-based endpoint (works even if workflow was deleted)
            let url = apiClient.baseURL
                .appendingPathComponent("workflow-execution")
                .appendingPathComponent("threads")
                .appendingPathComponent(threadId)
                .appendingPathComponent("diagram.png")

            var request = URLRequest(url: url)
            request.httpMethod = "GET"
            request.addEngineAuth(libraryPath: apiClient.currentLibraryPath)

            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                throw NSError(domain: "ActivityDiagramView", code: -1,
                              userInfo: [NSLocalizedDescriptionKey: "Invalid response"])
            }

            if httpResponse.statusCode == 200 {
                if let image = NSImage(data: data) {
                    diagramImage = image
                } else {
                    error = "Failed to decode image"
                }
            } else if httpResponse.statusCode == 404 {
                error = "Workflow not found"
            } else {
                if let errorJson = try? JSONDecoder().decode([String: String].self, from: data),
                   let detail = errorJson["detail"] {
                    error = detail
                } else {
                    error = "Server error: \(httpResponse.statusCode)"
                }
            }
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

    ActivityDiagramView(selectedRun: selectedRun)
        .environmentObject(library.apiClient)
        .frame(width: 600, height: 500)
}
