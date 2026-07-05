import OSLog
import SwiftUI

let activityProgressLogger = Logger(subsystem: "app.fichero.fichero", category: "ActivityProgressView")

// MARK: - View

/// Progress view showing workflow execution progress
struct ActivityProgressView: View {
    let selectedRun: SelectedActivityRun
    let liveExecution: WorkflowExecution?
    @Environment(APIClient.self) var apiClient
    @Environment(DocumentStore.self) var documentStore: DocumentStore

    /// Shared live-execution store (#2546). Optional so the view never crashes
    /// where the store isn't injected (e.g. previews).
    @Environment(WorkflowExecutionStore.self) var executionStore: WorkflowExecutionStore?

    @State var progressTimeline: ProgressTimeline?
    @State var isLoadingTimeline = false

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                if let execution = liveExecution {
                    liveProgressView(execution)
                } else {
                    historicalProgressView
                }
            }
            .padding()
        }
        .task {
            if liveExecution == nil {
                await loadProgressTimeline()
            }
        }
        .onChange(of: selectedRun.threadId) { _, _ in
            if liveExecution == nil {
                Task { await loadProgressTimeline() }
            }
        }
    }
}
