import SwiftUI
import OSLog

let comparisonDetailLogger = Logger(subsystem: "ca.tubb.Fichero", category: "ComparisonDetailView")

/// Detail view for a model comparison showing all model responses
struct ComparisonDetailView: View {
    let comparisonSummary: ComparisonSummary
    @EnvironmentObject var apiClient: APIClient

    @State var comparison: ComparisonDetail?
    @State var isLoading = true
    @State var error: String?
    @State var selectedModelId: String?
    @State var showRawJSON = false

    var body: some View {
        Group {
            if isLoading {
                ProgressView("Loading comparison...")
            } else if let error = error {
                errorView(error)
            } else if let comparison = comparison {
                comparisonContent(comparison)
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadComparison()
        }
    }
}

#Preview {
    ComparisonDetailView(
        comparisonSummary: ComparisonSummary(
            prompt: "What is the meaning of life?",
            modelsCompared: ["gpt-4o", "claude-3-5-sonnet-20241022"],
            totalCostUsd: 0.0042,
            comparisonId: "test-123",
            timestamp: "2024-01-25T14:30:00Z"
        )
    )
    .environmentObject(APIClient())
    .frame(width: 800, height: 600)
}
