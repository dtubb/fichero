import SwiftUI
import OSLog

let activityProgressLogger = Logger(subsystem: "ca.tubb.Fichero", category: "ActivityProgressView")

// MARK: - View

/// Progress view showing workflow execution progress
struct ActivityProgressView: View {
    let selectedRun: SelectedActivityRun
    let liveExecution: WorkflowExecution?
    @EnvironmentObject var apiClient: APIClient

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
