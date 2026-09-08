@testable import Fichero
import Testing

struct TranscribeNodeConfigTests {
    @Test("Transcribe language picker exposes canonical locales")
    func languagePickerLocales() {
        let codes = Set(TranscribeLanguageChoice.all.map(\.code))

        #expect(codes.contains("en-US"))
        #expect(codes.contains("auto"))
        #expect(codes.contains("es-ES"))
        #expect(codes.contains("es-MX"))
        #expect(TranscribeLanguageChoice.normalize("es") == "es-ES")
        #expect(TranscribeLanguageChoice.normalize("es_mx") == "es-MX")
        #expect(TranscribeLanguageChoice.normalize("en") == "en-US")
        #expect(TranscribeLanguageChoice.normalize("auto") == "auto")
        #expect(TranscribeNodeConfig.defaultMaxImageDimension == 2048)
    }

    // Spec: docs/contributor/specs/workflow-node-config.md
    // `nodeconfig.fields.transcribe.prompt.llm-only` + `nodeconfig.model.auto-mode-representation`

    @Test("LLM-only fields show for every mode that reaches an LLM: llm, auto, alias")
    func llmFieldsShowForLLMPaths() {
        // Explicit LLM mode.
        #expect(TranscribeNodeConfig.showsLLMFields(
            config: ["vision_mode": .string("llm")], providerName: "openai"))
        // Server default for a NEW node: auto resolves to an LLM unless the
        // resolved provider is Apple, so the prompt must be visible.
        #expect(TranscribeNodeConfig.showsLLMFields(
            config: ["vision_mode": .string("auto")], providerName: nil))
        // Alias selection drops vision_mode and carries the alias as provider.
        #expect(TranscribeNodeConfig.showsLLMFields(
            config: ["language": .string("es-ES")], providerName: "$vision_large"))
        #expect(TranscribeNodeConfig.showsLLMFields(config: nil, providerName: "$small"))
    }

    @Test("LLM-only fields hide when a recognition engine reads the page")
    func llmFieldsHideForRecognitionEngines() {
        #expect(!TranscribeNodeConfig.showsLLMFields(
            config: ["vision_mode": .string("apple")], providerName: nil))
        #expect(!TranscribeNodeConfig.showsLLMFields(
            config: ["vision_mode": .string("kraken")], providerName: nil))
        // No mode and no provider: the popover pre-selects Apple Vision.
        #expect(!TranscribeNodeConfig.showsLLMFields(config: nil, providerName: nil))
        #expect(!TranscribeNodeConfig.showsLLMFields(config: [:], providerName: nil))
    }
}
