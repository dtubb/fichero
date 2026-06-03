@testable import Fichero
import Testing

struct TranscribeNodeConfigTests {
    @Test("Transcribe language picker exposes canonical locales")
    func languagePickerLocales() {
        let codes = Set(TranscribeLanguageChoice.all.map(\.code))

        #expect(codes.contains("en-US"))
        #expect(codes.contains("es-ES"))
        #expect(codes.contains("es-MX"))
        #expect(TranscribeLanguageChoice.normalize("es") == "es-ES")
        #expect(TranscribeLanguageChoice.normalize("es_mx") == "es-MX")
        #expect(TranscribeLanguageChoice.normalize("en") == "en-US")
    }

    @Test("Apple Vision provider configures on-device OCR")
    func appleVisionProviderSelection() {
        var node = WorkflowNode(tool: "transcribe", config: ["vision_mode": .string("llm")])

        let selectedModel = node.applyProviderSelection(
            providerId: appleVisionProviderId,
            providers: [],
            toolRequiresVision: true,
            toolSupportsAppleVision: true
        )

        #expect(selectedModel.isEmpty)
        #expect(node.providerName == nil)
        #expect(node.modelName == nil)
        #expect(node.usesLLM == false)
        #expect(node.config?["vision_mode"]?.stringValue == "apple")
    }

    @Test("LLM provider configures vision LLM mode and first model")
    func llmProviderSelection() {
        let providers = [
            NodeProviderModelSelector.ProviderOption(
                id: "openai-id",
                name: "OpenAI",
                providerType: "openai",
                available: true,
                supportsVision: true,
                models: ["gpt-4o", "gpt-4o-mini"]
            )
        ]
        var node = WorkflowNode(tool: "transcribe", config: ["vision_mode": .string("apple")])

        let selectedModel = node.applyProviderSelection(
            providerId: "openai-id",
            providers: providers,
            toolRequiresVision: true,
            toolSupportsAppleVision: true
        )

        #expect(selectedModel == "gpt-4o")
        #expect(node.providerName == "openai-id")
        #expect(node.modelName == "gpt-4o")
        #expect(node.usesLLM == true)
        #expect(node.config?["vision_mode"]?.stringValue == "llm")
    }

    @Test("Tier alias configures vision LLM mode without model picker")
    func aliasProviderSelection() {
        var node = WorkflowNode(tool: "transcribe", config: ["vision_mode": .string("apple")])

        let selectedModel = node.applyProviderSelection(
            providerId: largeAliasProviderId,
            providers: [],
            toolRequiresVision: true,
            toolSupportsAppleVision: true
        )

        #expect(selectedModel.isEmpty)
        #expect(node.providerName == largeAliasProviderId)
        #expect(node.modelName == nil)
        #expect(node.usesLLM == true)
        #expect(node.config?["vision_mode"]?.stringValue == "llm")
    }

    @Test("Default provider clears stale explicit vision mode")
    func defaultProviderSelectionClearsVisionMode() {
        var node = WorkflowNode(
            tool: "transcribe",
            config: [
                "vision_mode": .string("llm"),
                "language": .string("es-ES")
            ],
            providerName: "openai-id",
            modelName: "gpt-4o",
            usesLLM: true
        )

        let selectedModel = node.applyProviderSelection(
            providerId: "",
            providers: [],
            toolRequiresVision: true,
            toolSupportsAppleVision: true
        )

        #expect(selectedModel.isEmpty)
        #expect(node.providerName == nil)
        #expect(node.modelName == nil)
        #expect(node.usesLLM == false)
        #expect(node.config?["vision_mode"] == nil)
        #expect(node.config?["language"]?.stringValue == "es-ES")
    }
}
