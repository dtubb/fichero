import SwiftUI

/// Toolbar for Workflow editor with run controls, canvas controls, and export
struct WorkflowToolbar: View {
    // Run state
    @Binding var isRunning: Bool
    @Binding var isSaving: Bool
    @Binding var showOutputLog: Bool
    let canRun: Bool

    // Canvas state
    @Binding var scale: CGFloat
    @Binding var snapToGrid: Bool

    // Actions
    let onRun: () -> Void
    let onSave: () async -> Void
    let onExport: () -> Void
    let onResetZoom: () -> Void
    var onPreviewDiagram: (() -> Void)? = nil
    var onRunOnDocuments: (() -> Void)? = nil

    var body: some View {
        HStack(spacing: 12) {
            // Canvas controls (left side)
            HStack(spacing: 8) {
                Text("Zoom: \(Int(scale * 100))%")
                    .font(.caption)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)

                Button(action: onResetZoom) {
                    Image(systemName: "arrow.clockwise")
                }
                .help("Reset Zoom")

                Toggle("Snap", isOn: $snapToGrid)
                    .toggleStyle(.button)
                    .help("Toggle Grid Snapping")
            }

            Spacer()

            // Workflow controls (right side)
            HStack(spacing: 8) {
                // Toggle output log
                Button(
                    action: { showOutputLog.toggle() },
                    label: {
                        Image(systemName: showOutputLog
                            ? "rectangle.bottomhalf.filled"
                            : "rectangle.bottomhalf.inset.filled")
                    }
                )
                .help(showOutputLog ? "Hide Output Log" : "Show Output Log")

                Divider()
                    .frame(height: 20)

                // Save
                Button(
                    action: {
                        Task {
                            await onSave()
                        }
                    },
                    label: {
                        if isSaving {
                            ProgressView()
                                .scaleEffect(0.7)
                        } else {
                            Image(systemName: "square.and.arrow.down")
                        }
                    }
                )
                .disabled(isSaving)
                .help(isSaving ? "Saving..." : "Save Workflow")

                // Export
                Button(action: onExport) {
                    Image(systemName: "square.and.arrow.up")
                }
                .help("Export Workflow")

                // Preview LangGraph diagram
                if let onPreview = onPreviewDiagram {
                    Button(action: onPreview) {
                        Image(systemName: "flowchart")
                    }
                    .help("Preview LangGraph Diagram")
                }

                // Run on Documents button
                if let onRunDocs = onRunOnDocuments {
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
