import SwiftUI

/// Sheet view showing the LangGraph visualization and Python code for a workflow
struct WorkflowDiagramPreview: View {
    let workflowId: String
    let workflowName: String
    @Binding var isPresented: Bool

    @Environment(WorkflowStore.self) var workflowStore

    @State private var diagramImage: PlatformImage?
    @State private var pythonCode: String?
    @State private var isLoading: Bool = true
    @State private var error: String?

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Workflow Diagram & Code")
                    .font(.headline)

                Spacer()

                Text(workflowName)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                Button("Done") {
                    isPresented = false
                }
                .keyboardShortcut(.escape)
            }
            .padding()
            .background(.bar)

            Divider()

            // Content - split view with diagram on left, code on right
            if isLoading {
                ProgressView("Loading diagram and code...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = error {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 48))
                        .foregroundStyle(.orange)
                    Text("Failed to load")
                        .font(.headline)
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                    Button("Retry") {
                        Task { @MainActor in
                            await loadContent()
                        }
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                PlatformHSplitView {
                    // Left: Diagram
                    VStack(spacing: 0) {
                        Text("LangGraph Diagram")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(.bar)

                        if let image = diagramImage {
                            ScrollView([.horizontal, .vertical]) {
                                Image(platformImage: image)
                                    .resizable()
                                    .aspectRatio(contentMode: .fit)
                                    .padding()
                            }
                            .background(Color(platformColor: .textBackgroundColor))
                        } else {
                            VStack {
                                Image(systemName: "flowchart")
                                    .font(.largeTitle)
                                    .foregroundStyle(.secondary)
                                Text("No diagram")
                                    .foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                        }
                    }
                    .frame(minWidth: 300)

                    // Right: Python Code
                    VStack(spacing: 0) {
                        HStack {
                            Text("Generated Python Code")
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            Spacer()

                            if pythonCode != nil {
                                Button {
                                    if let code = pythonCode {
                                        PlatformPasteboard.writeString(code)
                                    }
                                } label: {
                                    Image(systemName: "doc.on.doc")
                                }
                                .buttonStyle(.plain)
                                .help("Copy to clipboard")
                            }
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(.bar)

                        if let code = pythonCode {
                            ScrollView {
                                Text(code)
                                    .font(.system(.caption, design: .monospaced))
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(8)
                            }
                            .background(Color(platformColor: .textBackgroundColor))
                        } else {
                            VStack {
                                Image(systemName: "chevron.left.forwardslash.chevron.right")
                                    .font(.largeTitle)
                                    .foregroundStyle(.secondary)
                                Text("No code")
                                    .foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                        }
                    }
                    .frame(minWidth: 400)
                }
            }
        }
        .frame(minWidth: 900, minHeight: 600)
        .task {
            guard !Task.isCancelled else { return }
            await loadContent()
        }
    }

    private func loadContent() async {
        isLoading = true
        error = nil

        // Load diagram and code in parallel
        async let diagramTask: Void = loadDiagram()
        async let codeTask: Void = loadCode()

        await diagramTask
        await codeTask

        isLoading = false
    }

    private func loadDiagram() async {
        do {
            diagramImage = try await workflowStore.fetchWorkflowDiagramImage(workflowId)
        } catch {
            // Diagram loading failure is not fatal
        }
    }

    private func loadCode() async {
        do {
            pythonCode = try await workflowStore.fetchWorkflowPythonCode(workflowId)
        } catch {
            guard diagramImage == nil else { return }
            if let storeError = error as? WorkflowStoreError {
                switch storeError {
                case .executionFailed(let message):
                    self.error = message
                default:
                    self.error = error.localizedDescription
                }
            } else {
                self.error = error.localizedDescription
            }
        }
    }
}
