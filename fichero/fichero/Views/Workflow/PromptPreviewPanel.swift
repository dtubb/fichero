import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "PromptPreviewPanel")

/// Collapsible panel showing the fully assembled prompt for a workflow node.
/// Fetches from the backend `/tools/{tool}/prompt` endpoint and updates
/// live when the node config changes.
struct PromptPreviewPanel: View {
    let node: WorkflowNode
    @Environment(WorkflowService.self) var workflowService

    @State private var assembledPrompt: String?
    @State private var isLoading: Bool = false
    @State private var isExpanded: Bool = false
    @State private var loadError: String?

    /// Debounce timer to avoid hammering the API on every keystroke
    @State private var debounceTask: Task<Void, Never>?

    var body: some View {
        if node.usesLLM {
            DisclosureGroup("Prompt Preview", isExpanded: $isExpanded) {
                VStack(alignment: .leading, spacing: 8) {
                    if isLoading {
                        HStack(spacing: 6) {
                            ProgressView()
                                .controlSize(.small)
                            Text("Loading prompt...")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    } else if let error = loadError {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .font(.caption)
                            .foregroundColor(.orange)
                    } else if let prompt = assembledPrompt {
                        promptTextView(prompt)
                    } else {
                        Text("Expand to load prompt preview")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
                .padding(.top, 6)
            }
            .onChange(of: isExpanded) { _, expanded in
                if expanded {
                    fetchPrompt()
                }
            }
            .onChange(of: node.config) { _, _ in
                if isExpanded {
                    debouncedFetchPrompt()
                }
            }
        }
    }

    // MARK: - Prompt Display

    @ViewBuilder
    private func promptTextView(_ prompt: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            // Header with copy button
            HStack {
                Text("Assembled Prompt")
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .textCase(.uppercase)
                Spacer()
                Button {
                    PlatformPasteboard.writeString(prompt)
                } label: {
                    Image(systemName: "doc.on.doc")
                        .font(.caption2)
                }
                .buttonStyle(.plain)
                .foregroundColor(.secondary)
                .help("Copy prompt to clipboard")
            }

            // Prompt text in a styled container
            ScrollView {
                Text(prompt)
                    .font(.system(.caption, design: .monospaced))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
            }
            .frame(minHeight: 60, maxHeight: 160)
            .background(Color(.textBackgroundColor))
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color(.separatorColor), lineWidth: 1)
            )

            // Config indicator
            if let config = node.config, !config.isEmpty {
                let configKeys = config.keys.filter { $0 != "prompt" }.sorted()
                if !configKeys.isEmpty {
                    HStack(spacing: 4) {
                        Image(systemName: "slider.horizontal.3")
                            .font(.caption2)
                        Text(configKeys.joined(separator: ", "))
                            .font(.caption2)
                    }
                    .foregroundColor(.secondary)
                }
            }
        }
    }

    // MARK: - Fetch Logic

    private func fetchPrompt() {
        isLoading = true
        loadError = nil

        Task { @MainActor in
            do {
                let config = buildConfigDict()
                let prompt = try await workflowService.getToolPrompt(
                    toolName: node.tool,
                    config: config
                )
                assembledPrompt = prompt ?? workflowService.getToolInfo(named: node.tool)?.defaultPrompt
                loadError = nil
            } catch {
                logger.error("Failed to fetch prompt preview: \(String(describing: error))")
                // Fall back to default prompt from tool info
                assembledPrompt = workflowService.getToolInfo(named: node.tool)?.defaultPrompt
                if assembledPrompt == nil {
                    loadError = "Could not load prompt"
                }
            }
            isLoading = false
        }
    }

    private func debouncedFetchPrompt() {
        debounceTask?.cancel()
        debounceTask = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            fetchPrompt()
        }
    }

    /// Convert node config to [String: any Sendable] for the API call
    private func buildConfigDict() -> [String: any Sendable] {
        guard let config = node.config else { return [:] }
        var result: [String: any Sendable] = [:]
        for (key, value) in config {
            switch value {
            case .string(let str):
                result[key] = str
            case .int(let num):
                result[key] = num
            case .double(let num):
                result[key] = num
            case .bool(let flag):
                result[key] = flag
            default:
                break
            }
        }
        return result
    }
}
