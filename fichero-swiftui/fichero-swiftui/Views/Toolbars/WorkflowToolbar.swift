import SwiftUI

/// Toolbar for Workflow editor with run controls, canvas controls, and export
struct WorkflowToolbar: View {
    // Run state
    @Binding var isRunning: Bool
    let canRun: Bool

    // Actions
    let onRun: () -> Void
    let onExport: () -> Void
    var onPreviewDiagram: (() -> Void)?
    var onRunOnDocuments: (() -> Void)?
    @ObservedObject var featureManager = FeatureManager.shared

    var body: some View {
        HStack(spacing: 12) {
            Spacer(minLength: 0)

            // Workflow controls (right side)
            HStack(spacing: 8) {
                // Export
                if featureManager.isWorkflowImportExportEnabled {
                    Button(action: onExport) {
                        Image(systemName: "square.and.arrow.up")
                    }
                    .help("Export Workflow")
                }

                // Preview LangGraph diagram
                if let onPreview = onPreviewDiagram {
                    Button(action: onPreview) {
                        Image(systemName: "flowchart")
                    }
                    .help("Preview LangGraph Diagram")
                }

                // Run on Documents button
                if featureManager.isWorkflowFilesToolbarButtonEnabled, let onRunDocs = onRunOnDocuments {
                    Button(action: onRunDocs) {
                        Image(systemName: "doc.on.doc")
                    }
                    .help("Run on Documents...")
                }

                Divider()
                    .frame(height: 20)

                // Run button
                Button(action: onRun) {
                    if isRunning {
                        ProgressView()
                            .scaleEffect(0.7)
                    } else {
                        Image(systemName: "play.fill")
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(.green)
                .disabled(isRunning || !canRun)
                .help(isRunning ? "Running..." : "Run Workflow")
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(.ultraThinMaterial)
    }
}
