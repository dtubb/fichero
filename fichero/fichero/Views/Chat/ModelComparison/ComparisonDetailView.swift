import OSLog
import SwiftUI

let comparisonDetailLogger = Logger(subsystem: "app.fichero.fichero", category: "ComparisonDetailView")

/// Detail view for a model comparison showing all model responses.
///
/// Fetches through `ModelComparisonStore` (#5098: the observable-data-layer
/// guard — this view used to call the generated client directly; the fix
/// matches the sibling `ModelComparisonView`/`NodeComparisonSheet`, which
/// already each own their own store instance the same way).
struct ComparisonDetailView: View {
    let comparisonSummary: ComparisonSummary
    @Environment(APIClient.self) var apiClient

    // NOT `private`: this view is split across `+Actions`, `+Models` and `+Sections` files,
    // and a file-scope `private` is invisible to an extension in another file. Matches
    // `ModelComparisonView`, which is split the same way and declares it the same way.
    @State var store = ModelComparisonStore()
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
    .environment(APIClient())
    .environment(LibraryManager.shared)
    .frame(width: 800, height: 600)
}
