@testable import Fichero
import XCTest

/// FE↔BE parity for AIDefaults (#3220). The Swift struct claims to mirror the
/// backend Pydantic `AIDefaults` (settings.py). This decodes a full-field
/// snake_case payload — every tier the backend exposes, including the medium
/// and vision_* tiers that were previously missing — and asserts each maps, so
/// the next drift fails here instead of silently dead-ending a `$medium` /
/// `$vision_*` alias. Pure decode/encode, no live engine.
final class AIDefaultsParityTests: XCTestCase {

    /// A payload carrying every backend field with a distinct value, so a
    /// missing CodingKey shows up as a default "" mismatch.
    private let fullPayload = Data("""
    {
        "vision_provider": "vp", "vision_model": "vm",
        "text_provider": "tp", "text_model": "tm",
        "audio_provider": "ap", "audio_model": "am",
        "video_provider": "vidp", "video_model": "vidm",
        "embeddings_provider": "ep", "embeddings_model": "em",
        "small_provider": "sp", "small_model": "sm",
        "medium_provider": "mp", "medium_model": "mm",
        "large_provider": "lp", "large_model": "lm",
        "vision_small_provider": "vsp", "vision_small_model": "vsm",
        "vision_medium_provider": "vmp", "vision_medium_model": "vmm",
        "vision_large_provider": "vlp", "vision_large_model": "vlm",
        "temperature": "0.5", "max_tokens": "2048",
        "prompt_prefix": "PRE", "primary_language": "es"
    }
    """.utf8)

    func testDecodesEveryBackendTierField() throws {
        let decoded = try JSONDecoder().decode(AIDefaults.self, from: fullPayload)
        // Modality defaults.
        XCTAssertEqual(decoded.visionProvider, "vp"); XCTAssertEqual(decoded.visionModel, "vm")
        XCTAssertEqual(decoded.textProvider, "tp"); XCTAssertEqual(decoded.textModel, "tm")
        XCTAssertEqual(decoded.audioProvider, "ap"); XCTAssertEqual(decoded.audioModel, "am")
        XCTAssertEqual(decoded.videoProvider, "vidp"); XCTAssertEqual(decoded.videoModel, "vidm")
        XCTAssertEqual(decoded.embeddingsProvider, "ep"); XCTAssertEqual(decoded.embeddingsModel, "em")
        // Capability tiers — small/medium/large (medium was missing pre-#3220).
        XCTAssertEqual(decoded.smallProvider, "sp"); XCTAssertEqual(decoded.smallModel, "sm")
        XCTAssertEqual(decoded.mediumProvider, "mp"); XCTAssertEqual(decoded.mediumModel, "mm")
        XCTAssertEqual(decoded.largeProvider, "lp"); XCTAssertEqual(decoded.largeModel, "lm")
        // Vision tiers — all three were missing pre-#3220.
        XCTAssertEqual(decoded.visionSmallProvider, "vsp"); XCTAssertEqual(decoded.visionSmallModel, "vsm")
        XCTAssertEqual(decoded.visionMediumProvider, "vmp"); XCTAssertEqual(decoded.visionMediumModel, "vmm")
        XCTAssertEqual(decoded.visionLargeProvider, "vlp"); XCTAssertEqual(decoded.visionLargeModel, "vlm")
        // Scalars.
        XCTAssertEqual(decoded.temperature, "0.5"); XCTAssertEqual(decoded.maxTokens, "2048")
        XCTAssertEqual(decoded.promptPrefix, "PRE"); XCTAssertEqual(decoded.primaryLanguage, "es")
    }

    /// Encode→decode round-trips through the snake_case keys (Equatable).
    func testRoundTripPreservesAllTiers() throws {
        let original = try JSONDecoder().decode(AIDefaults.self, from: fullPayload)
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(AIDefaults.self, from: data)
        XCTAssertEqual(decoded, original)
    }

    /// The new tier fields encode under their snake_case wire keys, so a PUT
    /// round-trips to the backend without dropping them.
    func testNewTiersEncodeSnakeCase() throws {
        var defaults = AIDefaults()
        defaults.mediumProvider = "mp"
        defaults.visionMediumModel = "vmm"
        let obj = try XCTUnwrap(
            JSONSerialization.jsonObject(with: try JSONEncoder().encode(defaults)) as? [String: Any]
        )
        XCTAssertEqual(obj["medium_provider"] as? String, "mp")
        XCTAssertEqual(obj["vision_medium_model"] as? String, "vmm")
        XCTAssertNil(obj["mediumProvider"])  // camelCase never leaks
    }
}
