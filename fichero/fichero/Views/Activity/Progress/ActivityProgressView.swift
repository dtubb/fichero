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

    /// A reopened FINISHED run still resolves a liveExecution with cleared
    /// state — the live branch then renders a bare "Overall Progress" header
    /// (Daniel 2026-08-15). Live means running, or state worth showing;
    /// otherwise the HISTORICAL loader owns this tab.
    private var showsLive: Bool {
        guard let execution = liveExecution else { return false }
        return execution.isRunning || !execution.orderedDocumentProgress.isEmpty
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                if showsLive, let execution = liveExecution {
                    liveProgressView(execution)
                } else {
                    historicalProgressView
                }
            }
            .padding()
        }
        .task {
            if !showsLive {
                await loadProgressTimeline()
            }
        }
        .onChange(of: selectedRun.threadId) { _, _ in
            if !showsLive {
                Task { await loadProgressTimeline() }
            }
        }
    }
}
