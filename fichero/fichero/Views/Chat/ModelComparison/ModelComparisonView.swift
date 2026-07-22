import OSLog
import SwiftUI

struct ModelComparisonView: View {
    @State var store = ModelComparisonStore()
    @State var prompt = ""
    @State var systemPrompt = ""
    @State var selectedModels: [ModelSpec] = [
        ModelSpec(provider: "openai", model: "gpt-4o"),
        ModelSpec(provider: "anthropic", model: "claude-3-5-sonnet-20241022")
    ]
    @State var showingModelPicker = false
    @State var showingPresets = false

    var body: some View {
        NavigationSplitView {
            sidebar
                .navigationSplitViewColumnWidth(min: 250, ideal: 300)
        } detail: {
            if let result = store.lastResult {
                ComparisonResultView(result: result)
            } else {
                ContentUnavailableView(
                    "No Comparison",
                    systemImage: "square.split.2x2",
                    description: Text("Enter a prompt and select models to compare")
                )
            }
        }
        .task {
            await store.loadModels()
            await store.loadPresets()
        }
    }
}

#Preview {
    ModelComparisonView()
}
