import SwiftUI

/// Toolbar for Workflow editor with run controls, canvas controls, and export
struct WorkflowToolbar: View {
    // Run state
    @Binding var isRunning: Bool
    let canRun: Bool

    // Input source (workflow-level batch config)
    @Binding var inputSource: WorkflowInputSource

    // Actions
    let onRun: () -> Void
    let onImport: () -> Void
    let onExport: () -> Void
    var onPreviewDiagram: (() -> Void)?
    var onRunOnDocuments: (() -> Void)?
    var onCompareModels: (() -> Void)?
    @ObservedObject var featureManager = FeatureManager.shared

    var body: some View {
        HStack(spacing: 12) {
            // Input source picker (left side)
            HStack(spacing: 4) {
                Image(systemName: inputSource.icon)
                    .font(.caption)
                    .foregroundColor(.secondary)
                Picker("Input", selection: $inputSource) {
                    ForEach(WorkflowInputSource.allCases, id: \.self) { source in
                        Label(source.displayName, systemImage: source.icon)
                            .tag(source)
                    }
                }
                .pickerStyle(.menu)
                .fixedSize()
                .help(inputSource.helpText)
            }

            Spacer(minLength: 0)

            // Workflow controls (right side)
            HStack(spacing: 8) {
                // Export
                if featureManager.isWorkflowImportExportEnabled {
                    Button(action: onImport) {
                        Image(systemName: "square.and.arrow.down")
                    }
                    .help("Import Workflow")

                    Button(action: onExport) {
                        Image(systemName: "square.and.arrow.up")
                    }
                    .help("Export Workflow")
                }

                // Preview LangGraph diagram
                if featureManager.isWorkflowLangGraphPreviewEnabled, let onPreview = onPreviewDiagram {
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

                if let onCompareModels {
                    Button(action: onCompareModels) {
                        Image(systemName: "square.split.2x2")
                    }
                    .help("Compare Models...")
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
        .background(Color(.controlBackgroundColor))
    }
}
