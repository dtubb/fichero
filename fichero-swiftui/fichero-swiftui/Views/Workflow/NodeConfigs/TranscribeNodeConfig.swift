import SwiftUI

/// Configuration view for transcribe node
///
/// The Vision Engine toggle has been removed — Apple Vision is now a provider
/// option in the unified provider/model selector (see NodeProviderModelSelector).
struct TranscribeNodeConfig: View {
    @Binding var node: WorkflowNode

    let toolInfo: ToolInfo?
    let backendPrompt: String?

    @State private var language: String = "en"
    @State private var maxImageDimension: Double = 11024
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

    /// Whether the node is currently configured for LLM mode (not Apple Vision)
    private var isLLMMode: Bool {
        if let configValue = node.config?["vision_mode"],
           case .string(let mode) = configValue {
            return mode == "llm"
        }
        // Default: Apple Vision (not LLM mode)
        return false
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Language (always shown — relevant for both Apple Vision and LLM)
            VStack(alignment: .leading, spacing: 4) {
                Text("Language")
                    .font(.caption)
                    .foregroundColor(.secondary)

                TextField("Language code (e.g., en, es, fr)", text: $language)
                    .textFieldStyle(.roundedBorder)
                    .onChange(of: language) { _, newValue in
                        if node.config == nil {
                            node.config = [:]
                        }
                        node.config?["language"] = .string(newValue)
                    }
            }

            // Image Size (only for LLM mode)
            if isLLMMode {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Max Image Size")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    Picker("Max Image Size", selection: $maxImageDimension) {
                        Text("512px (Fastest)").tag(512.0)
                        Text("768px (Fast)").tag(768.0)
                        Text("1024px (Balanced)").tag(1024.0)
                        Text("1536px (Detailed)").tag(1536.0)
                        Text("2048px").tag(2048.0)
                        Text("11024px (Default)").tag(11024.0)
                        Text("Original Size (Maximum)").tag(0.0)
                    }
                    .pickerStyle(.menu)
                    .onChange(of: maxImageDimension) { _, newValue in
                        if node.config == nil {
                            node.config = [:]
                        }
                        node.config?["max_image_dimension"] = .int(Int(newValue))
                    }

                    Text("Smaller = faster, original = full detail")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }

            // Custom prompt (only for LLM mode)
            if isLLMMode {
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
        if let configValue = node.config?["language"],
           case .string(let lang) = configValue {
            language = lang
        }

        if let configValue = node.config?["max_image_dimension"],
           case .int(let dimension) = configValue {
            maxImageDimension = Double(dimension)
        }

        if let configValue = node.config?["prompt"],
           case .string(let prompt) = configValue {
            promptText = prompt
        } else if let defaultPrompt = currentDefaultPrompt {
            promptText = defaultPrompt
        }
    }
}
