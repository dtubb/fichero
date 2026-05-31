@testable import Fichero
import XCTest

final class AIDefaultsTests: XCTestCase {
    func testSeedAppleDefaultsFillsEmptySlots() {
        var defaults = AIDefaults()

        defaults.seedAppleDefaultsIfNeeded(appleAvailable: true)

        XCTAssertEqual(defaults.textProvider, "apple")
        XCTAssertEqual(defaults.textModel, "apple-intelligence")
        XCTAssertEqual(defaults.visionProvider, "apple")
        XCTAssertEqual(defaults.visionModel, "apple-vision")
        XCTAssertEqual(defaults.audioProvider, "apple")
        XCTAssertEqual(defaults.audioModel, "apple-speech")
        XCTAssertEqual(defaults.smallProvider, "apple")
        XCTAssertEqual(defaults.smallModel, "apple-intelligence")
        XCTAssertEqual(defaults.largeProvider, "apple")
        XCTAssertEqual(defaults.largeModel, "apple-intelligence")
    }

    func testSeedAppleDefaultsDoesNotOverwriteNonEmptyValues() {
        var defaults = AIDefaults(
            visionProvider: "openai",
            visionModel: "gpt-4o",
            textProvider: "anthropic",
            textModel: "claude-3-5-sonnet-20241022",
            audioProvider: "openrouter",
            audioModel: "whisper-large-v3",
            videoProvider: "",
            videoModel: "",
            embeddingsProvider: "",
            embeddingsModel: "",
            smallProvider: "openai",
            smallModel: "gpt-4o-mini",
            largeProvider: "openai",
            largeModel: "gpt-4o",
            temperature: "",
            maxTokens: "",
            promptPrefix: ""
        )

        defaults.seedAppleDefaultsIfNeeded(appleAvailable: true)

        XCTAssertEqual(defaults.textProvider, "anthropic")
        XCTAssertEqual(defaults.textModel, "claude-3-5-sonnet-20241022")
        XCTAssertEqual(defaults.visionProvider, "openai")
        XCTAssertEqual(defaults.visionModel, "gpt-4o")
        XCTAssertEqual(defaults.audioProvider, "openrouter")
        XCTAssertEqual(defaults.audioModel, "whisper-large-v3")
        XCTAssertEqual(defaults.smallProvider, "openai")
        XCTAssertEqual(defaults.smallModel, "gpt-4o-mini")
        XCTAssertEqual(defaults.largeProvider, "openai")
        XCTAssertEqual(defaults.largeModel, "gpt-4o")
    }

    func testSeedAppleDefaultsNoopWhenAppleUnavailable() {
        var defaults = AIDefaults()

        defaults.seedAppleDefaultsIfNeeded(appleAvailable: false)

        XCTAssertEqual(defaults, AIDefaults())
    }
}
