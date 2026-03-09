import SwiftUI

/// Configuration view for transcribe node
struct TranscribeNodeConfig: View {
    @Binding var node: WorkflowNode

    let toolInfo: ToolInfo?
    let backendPrompt: String?

    @State private var visionMode: String = "apple"
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

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Vision Mode selector
            VStack(alignment: .leading, spacing: 4) {
                Text("Vision Engine")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Picker("Vision Engine", selection: $visionMode) {
                    Label("Apple Vision (On-Device)", systemImage: "apple.logo")
                        .tag("apple")
                    Label("Vision LLM (Cloud)", systemImage: "cloud")
                        .tag("llm")
                }
                .pickerStyle(.menu)
                .onChange(of: visionMode) { _, newValue in
                    if node.config == nil {
                        node.config = [:]
                    }
                    node.config?["vision_mode"] = .string(newValue)
                    node.usesLLM = (newValue == "llm")
                    // Clear provider/model when switching to Apple Vision
                    if newValue == "apple" {
                        node.providerName = nil
                        node.modelName = nil
                    }
                }
            }

            // Language
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
            if visionMode == "llm" {
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
            if visionMode == "llm" {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Prompt")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    TextEditor(text: $promptText)
                        .font(.caption)
                        .scrollContentBackground(.hidden)
                        .background(Color.clear)
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
        if let configValue = node.config?["vision_mode"],
           case .string(let mode) = configValue {
            visionMode = mode
        }

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
