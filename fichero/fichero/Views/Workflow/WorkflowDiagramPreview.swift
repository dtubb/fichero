import FicheroAPIClient
import SwiftUI

/// Sheet view showing the LangGraph visualization and Python code for a workflow
struct WorkflowDiagramPreview: View {
    let workflowId: String
    let workflowName: String
    @Binding var isPresented: Bool

    @EnvironmentObject var apiClient: APIClient

    @State private var diagramImage: NSImage?
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
                HSplitView {
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
                                Image(nsImage: image)
                                    .resizable()
                                    .aspectRatio(contentMode: .fit)
                                    .padding()
                            }
                            .background(Color(nsColor: .textBackgroundColor))
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
                                        NSPasteboard.general.clearContents()
                                        NSPasteboard.general.setString(code, forType: .string)
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
                            .background(Color(nsColor: .textBackgroundColor))
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
            let url = apiClient.baseURL
                .appendingPathComponent("workflow-execution")
                .appendingPathComponent("workflows")
                .appendingPathComponent(workflowId)
                .appendingPathComponent("visualization.png")

            var request = URLRequest(url: url)
            request.httpMethod = "GET"
            request.addEngineAuth(libraryPath: apiClient.currentLibraryPath)

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
                return
            }
            diagramImage = NSImage(data: data)
        } catch {
            // Diagram loading failure is not fatal
        }
    }

    private func loadCode() async {
        do {
            // Route the JSON code fetch through the generated client (#1714).
            // The co-located PNG download in `loadDiagram()` stays raw URLSession
            // (binary image, not modellable through the generated client).
            let client = makeGeneratedClient()
            let response = try await client.api.getWorkflowCodeApiWorkflowExecutionWorkflowsWorkflowIdCodeGet(.init(
                path: .init(workflowId: workflowId),
                headers: .init(xFicheroLibraryPath: apiClient.currentLibraryPath ?? "")
            ))
            switch response {
            case .ok(let okResponse):
                pythonCode = try okResponse.body.json.pythonCode
            case .unprocessableContent:
                self.error = "Validation error"
            case .undocumented(let statusCode, _):
                self.error = "Failed to load code (HTTP \(statusCode))"
            }
        } catch {
            // Code loading failure sets error only if diagram also failed
            if diagramImage == nil {
                self.error = error.localizedDescription
            }
        }
    }

    /// Build a generated client from the injected `APIClient` host + library path.
    /// `apiClient.baseURL` carries the `/api` suffix; FicheroClient expects the host
    /// root (openapi paths already include `/api`), so strip the path here.
    private func makeGeneratedClient() -> FicheroClient {
        var components = URLComponents(url: apiClient.baseURL, resolvingAgainstBaseURL: false)
        components?.path = ""
        let host = components?.url ?? apiClient.baseURL
        return FicheroClient(baseURL: host, libraryPath: apiClient.currentLibraryPath)
    }
}
