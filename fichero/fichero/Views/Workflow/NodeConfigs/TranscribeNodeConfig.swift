import SwiftUI

/// Configuration view for transcribe node
///
/// The Vision Engine toggle has been removed — Apple Vision is now a provider
/// option in the unified provider/model selector (see NodeProviderModelSelector).
struct TranscribeLanguageChoice: Identifiable, Hashable {
    let code: String
    let label: String

    var id: String { code }

    static let defaultCode = "en-US"

    static let all: [TranscribeLanguageChoice] = [
        .init(code: "en-US", label: "English (United States)"),
        .init(code: "es-ES", label: "Spanish (Spain)"),
        .init(code: "es-MX", label: "Spanish (Mexico)"),
        .init(code: "fr-FR", label: "French (France)"),
        .init(code: "de-DE", label: "German (Germany)"),
        .init(code: "it-IT", label: "Italian (Italy)"),
        .init(code: "pt-BR", label: "Portuguese (Brazil)"),
        .init(code: "ja-JP", label: "Japanese (Japan)"),
        .init(code: "ko-KR", label: "Korean (South Korea)")
    ]

    static func normalize(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return defaultCode }

        let replaced = trimmed.replacingOccurrences(of: "_", with: "-")
        let lowered = replaced.lowercased()
        let legacyAliases = [
            "en": "en-US",
            "es": "es-ES",
            "fr": "fr-FR",
            "de": "de-DE",
            "it": "it-IT",
            "pt": "pt-BR",
            "ja": "ja-JP",
            "ko": "ko-KR"
        ]

        if let alias = legacyAliases[lowered] {
            return alias
        }

        if let dashIndex = replaced.firstIndex(of: "-") {
            let base = replaced[..<dashIndex].lowercased()
            let suffix = replaced[replaced.index(after: dashIndex)...]
            if suffix.count == 2 {
                return "\(base)-\(suffix.uppercased())"
            }
            return "\(base)-\(suffix)"
        }

        return replaced
    }
}

struct TranscribeNodeConfig: View {
    @Binding var node: WorkflowNode

    let toolInfo: ToolInfo?
    let backendPrompt: String?

    @State private var language: String = TranscribeLanguageChoice.defaultCode
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
                Text("Language / Locale")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Picker("Language / Locale", selection: $language) {
                    ForEach(TranscribeLanguageChoice.all) { choice in
                        Text(choice.label).tag(choice.code)
                    }
                }
                .pickerStyle(.menu)
                .onChange(of: language) { _, newValue in
                    if node.config == nil {
                        node.config = [:]
                    }
                    node.config?["language"] = .string(newValue)
                }

                Text("Spanish on Apple Intelligence often needs a locale like es-ES or es-MX.")
                    .font(.caption2)
                    .foregroundColor(.secondary)
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
            language = TranscribeLanguageChoice.normalize(lang)
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
