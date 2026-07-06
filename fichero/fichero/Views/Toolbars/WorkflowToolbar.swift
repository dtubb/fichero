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
        MiniToolbar {
            inputSourcePicker
            Spacer(minLength: 0)
            ViewThatFits(in: .horizontal) {
                actionButtons
                overflowMenu
            }
        }
    }

    private var inputSourcePicker: some View {
        HStack(spacing: 4) {
            Image(systemName: inputSource.icon)
                .font(.caption)
                .foregroundStyle(.secondary)
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
    }

    private var actionButtons: some View {
        HStack(spacing: 8) {
            if featureManager.isWorkflowImportExportEnabled {
                Button(action: onImport) {
                    Image(systemName: "square.and.arrow.down")
                }
                .buttonStyle(.plain)
                .help("Import Workflow")
                .accessibilityLabel("Import Workflow")

                Button(action: onExport) {
                    Image(systemName: "square.and.arrow.up")
                }
                .buttonStyle(.plain)
                .help("Export Workflow")
                .accessibilityLabel("Export Workflow")
            }

            if featureManager.isWorkflowLangGraphPreviewEnabled, let onPreview = onPreviewDiagram {
                Button(action: onPreview) {
                    Image(systemName: "flowchart")
                }
                .buttonStyle(.plain)
                .help("Preview LangGraph Diagram")
                .accessibilityLabel("Preview LangGraph Diagram")
            }

            if featureManager.isWorkflowFilesToolbarButtonEnabled, let onRunDocs = onRunOnDocuments {
                Button(action: onRunDocs) {
                    Image(systemName: "doc.on.doc")
                }
                .buttonStyle(.plain)
                .help("Run on Documents")
                .accessibilityLabel("Run on Documents")
            }

            if let onCompareModels {
                Button(action: onCompareModels) {
                    Image(systemName: "square.split.2x2")
                }
                .buttonStyle(.plain)
                .help("Compare Models")
                .accessibilityLabel("Compare Models")
            }

            Divider()
                .frame(height: 16)

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
            .help(isRunning ? "Running" : "Run Workflow")
            .accessibilityLabel(isRunning ? "Running" : "Run Workflow")
        }
    }

    private var overflowMenu: some View {
        Menu {
            if featureManager.isWorkflowImportExportEnabled {
                Button(action: onImport) {
                    Label("Import Workflow", systemImage: "square.and.arrow.down")
                }
                Button(action: onExport) {
                    Label("Export Workflow", systemImage: "square.and.arrow.up")
                }
            }
            if featureManager.isWorkflowLangGraphPreviewEnabled, let onPreview = onPreviewDiagram {
                Button(action: onPreview) {
                    Label("Preview Diagram", systemImage: "flowchart")
                }
            }
            if featureManager.isWorkflowFilesToolbarButtonEnabled, let onRunDocs = onRunOnDocuments {
                Button(action: onRunDocs) {
                    Label("Run on Documents", systemImage: "doc.on.doc")
                }
            }
            if let onCompareModels {
                Button(action: onCompareModels) {
                    Label("Compare Models", systemImage: "square.split.2x2")
                }
            }
            Button(action: onRun) {
                Label(isRunning ? "Running" : "Run Workflow", systemImage: "play.fill")
            }
            .disabled(isRunning || !canRun)
        } label: {
            Image(systemName: "ellipsis.circle")
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .help("Workflow Actions")
        .accessibilityLabel("Workflow Actions")
    }
}
