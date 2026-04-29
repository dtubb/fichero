import SwiftUI

/// Configuration view for describe node
struct DescribeNodeConfig: View {
    @Binding var node: WorkflowNode

    let toolInfo: ToolInfo?
    let backendPrompt: String?

    @State private var detailLevel: String = "detailed"
    @State private var focusText: String = ""
    @State private var promptText: String = ""

    /// Get the current default prompt - from backend if available, otherwise nil
    private var currentDefaultPrompt: String? {
        // Use dynamically fetched prompt if available
        if let prompt = backendPrompt {
            return prompt
        }
        // Fall back to static default from tool info
        return toolInfo?.defaultPrompt
    }

    var body: some View {
        // Describe tool ONLY supports LLM vision (no Apple Vision)
        // The backend hardcodes vision_mode="llm" since it requires semantic understanding
        VStack(alignment: .leading, spacing: 12) {
            // Detail level
            VStack(alignment: .leading, spacing: 4) {
                Text("Detail Level")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Picker("", selection: $detailLevel) {
                    Text("Brief").tag("brief")
                    Text("Detailed").tag("detailed")
                    Text("Comprehensive").tag("comprehensive")
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .onChange(of: detailLevel) { _, newValue in
                    if node.config == nil {
                        node.config = [:]
                    }
                    node.config?["detail_level"] = .string(newValue)
                }
            }

            // Focus
            VStack(alignment: .leading, spacing: 4) {
                Text("Focus (optional)")
                    .font(.caption)
                    .foregroundColor(.secondary)

                TextField("e.g., people, objects, text, scene", text: $focusText)
                    .textFieldStyle(.roundedBorder)
                    .onChange(of: focusText) { _, newValue in
                        if newValue.isEmpty {
                            node.config?.removeValue(forKey: "focus")
                        } else {
                            if node.config == nil {
                                node.config = [:]
                            }
                            node.config?["focus"] = .string(newValue)
                        }
                    }
            }

            // Thinking mode
            ThinkingModePicker(node: $node)

            // Custom prompt
            VStack(alignment: .leading, spacing: 4) {
                Text("Prompt")
                    .font(.caption)
                    .foregroundColor(.secondary)

                MacPlainTextEditor(text: $promptText, font: .preferredFont(forTextStyle: .caption1))
                    .frame(minHeight: 80)
                    .background(Color(.textBackgroundColor))
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color(.separatorColor), lineWidth: 1)
                    )
                    .onChange(of: promptText) { _, newValue in
                        if newValue.isEmpty {
                            node.config?.removeValue(forKey: "prompt")
                        } else {
                            if node.config == nil {
                                node.config = [:]
                            }
                            node.config?["prompt"] = .string(newValue)
                        }
                    }

                Text("Prompt is editable. Clear to restore tool default.")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
        }
        .onAppear {
            loadInitialState()
        }
        .onChange(of: backendPrompt) { _, newDefault in
            // When backend prompt arrives asynchronously, populate editor only
            // if user has not customized prompt yet.
            guard promptText.isEmpty,
                  node.config?["prompt"] == nil,
                  let newDefault,
                  !newDefault.isEmpty else { return }
            promptText = newDefault
        }
    }

    private func loadInitialState() {
        if let configValue = node.config?["detail_level"],
           case .string(let level) = configValue {
            detailLevel = level
        }

        if let configValue = node.config?["focus"],
           case .string(let focus) = configValue {
            focusText = focus
        }

        if let configValue = node.config?["prompt"],
           case .string(let prompt) = configValue {
            promptText = prompt
        } else if let defaultPrompt = currentDefaultPrompt {
            promptText = defaultPrompt
        }
    }
}
