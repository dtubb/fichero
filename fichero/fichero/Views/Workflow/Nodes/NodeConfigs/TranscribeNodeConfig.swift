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
        .init(code: "auto", label: "Auto-Detect"),
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
    // `nonisolated` is PRECAUTIONARY here (unlike OntologyBrowser's, which
    // fixed a live trap): an immutable Sendable static is readable off-main
    // today. Marked for consistency — statics on View types inherit
    // MainActor under the macOS 26 SDK, and this is read from a Swift
    // Testing suite that runs on cooperative-pool threads.
    nonisolated static let defaultMaxImageDimension = 2048.0

    @Binding var node: WorkflowNode

    let toolInfo: ToolInfo?
    let backendPrompt: String?

    @State private var language: String = TranscribeLanguageChoice.defaultCode
    @State private var maxImageDimension: Double = TranscribeNodeConfig.defaultMaxImageDimension

    /// Whether the run will go through an LLM, so the LLM-only fields (prompt,
    /// image size) apply. Spec `nodeconfig.fields.transcribe.prompt.llm-only`.
    ///
    /// Mirrors the engine (`vision_base.py`: `auto` → `apple` only when the
    /// resolved provider is Apple, else `llm`): `llm` and `auto` reach an LLM;
    /// `apple`/`kraken` are recognition engines. With no mode at all — the
    /// state a tier-alias selection leaves — a chosen provider/alias means
    /// LLM; nothing chosen means the popover's Apple Vision default. Gating on
    /// the literal "llm" used to hide the prompt for every NEW node (server
    /// default is "auto") and every alias-configured node.
    nonisolated static func showsLLMFields(config: [String: AnyCodableValue]?, providerName: String?) -> Bool {
        switch config?["vision_mode"]?.stringValue {
        case "apple", "kraken": return false
        case "llm", "auto": return true
        default: return providerName != nil
        }
    }

    private var isLLMMode: Bool {
        Self.showsLLMFields(config: node.config, providerName: configuredNodeProviderId(node))
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
                        Text("2048px (Default)").tag(2048.0)
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

            // Prompt (only when an LLM reads the page). Ghost default, override
            // on edit — the one shared editor; nothing here writes config on appear.
            if isLLMMode {
                NodePromptEditor(
                    node: $node,
                    backendPrompt: backendPrompt,
                    registryPrompt: toolInfo?.defaultPrompt
                )
            }
        }
        .onAppear {
            loadInitialState()
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
    }
}
