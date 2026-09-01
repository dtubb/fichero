import XCTest
@testable import Fichero

/// Which models the Settings → AI Defaults pickers are allowed to withhold.
///
/// Daniel, 2026-09-01: "cannot select a model like Opus or Google — maybe
/// it's not got the right vision toggle." The Vision tier demanded an
/// explicit "vision" capability STRING, which only a user-configured row
/// carries; a model discovered from a live provider catalog, or one newer
/// than the vendored registry, arrives without it and was filtered out of
/// existence. A model the picker never lists is indistinguishable from a
/// model the provider does not ship.
final class AIDefaultsTierFilterTests: XCTestCase {

    private func model(
        _ id: String,
        vision: Bool = false,
        audio: Bool = false,
        capabilities: [String] = []
    ) throws -> ModelInfo {
        let json = """
        {
          "model_id": "\(id)", "full_name": "\(id)", "description": null,
          "is_recommended": false, "is_local": false,
          "input_cost_per_million": 0, "output_cost_per_million": 0,
          "batch_input_cost_per_million": null,
          "batch_output_cost_per_million": null,
          "cache_read_cost_per_million": null,
          "max_input_tokens": null, "max_output_tokens": null, "mode": "chat",
          "supports_vision": \(vision), "supports_function_calling": false,
          "supports_audio_input": \(audio), "supports_audio_output": false,
          "supports_pdf_input": false, "supports_prompt_caching": false,
          "supports_reasoning": false, "supports_web_search": false,
          "supports_streaming": true, "supports_batch_api": false,
          "provider": "test"
        }
        """
        var decoded = try JSONDecoder().decode(ModelInfo.self, from: Data(json.utf8))
        decoded.capabilities = capabilities
        return decoded
    }

    // MARK: - The bug

    func testVisionTierAcceptsAModelThatOnlyReportsTheSupportsVisionFlag() throws {
        // The discovery endpoint reports capabilities as `supports_*` bools and
        // leaves `capabilities` empty — that is the shape that vanished.
        let opus = try model("claude-opus-4-5", vision: true)
        XCTAssertTrue(AISettingsView.TierCapability.vision.matches(opus))
    }

    func testVisionTierAcceptsACapabilitylessModelFromAVisionFamily() throws {
        // Newer than the vendored registry: no flags at all, no strings.
        let future = try model("claude-opus-4-9-20260901")
        XCTAssertTrue(AISettingsView.TierCapability.vision.matches(future))
        let gemini = try model("gemini-4.0-pro")
        XCTAssertTrue(AISettingsView.TierCapability.vision.matches(gemini))
    }

    func testAudioTierAcceptsTheSupportsAudioInputFlag() throws {
        let whisper = try model("whisper-1", audio: true)
        XCTAssertTrue(AISettingsView.TierCapability.audio.matches(whisper))
    }

    // MARK: - The floor must not become a new lie

    func testACapabilitylessTextOnlyModelStillFailsTheVisionTier() throws {
        for id in ["text-embedding-3-large", "gemma-3-27b", "claude-2.1"] {
            let textOnly = try model(id)
            XCTAssertFalse(
                AISettingsView.TierCapability.vision.matches(textOnly),
                "\(id) must not be offered for the Vision tier"
            )
        }
    }

    func testAModelWithExplicitTextOnlyCapabilitiesStillFailsTheVisionTier() throws {
        // An explicit capability list is a STATEMENT — the family floor only
        // fills silence, so it must not override this.
        let stated = try model("claude-sonnet-4-5", capabilities: ["text", "tools"])
        XCTAssertFalse(AISettingsView.TierCapability.vision.matches(stated))
    }

    func testTextTierStillAcceptsCapabilitylessModels() throws {
        let unknown = try model("some-new-chat-model")
        XCTAssertTrue(AISettingsView.TierCapability.text.matches(unknown))
    }

    func testAnyTierFiltersNothing() throws {
        let anything = try model("whatever")
        XCTAssertTrue(AISettingsView.TierCapability.any.matches(anything))
    }

    // MARK: - The id floor itself

    func testIdFloorMirrorsTheEngineFamilies() {
        let floor = AISettingsView.TierCapability.idLooksVisionCapable
        XCTAssertTrue(floor("gpt-5.5"))
        XCTAssertTrue(floor("qwen3-vl-8b-instruct"))
        XCTAssertTrue(floor("pixtral-12b"))
        XCTAssertFalse(floor("text-embedding-3-large"))
        XCTAssertFalse(floor("claude-instant-1.2"))
        XCTAssertFalse(floor(""))
    }
}
