@testable import Fichero
import FicheroAPIClient
import XCTest

/// Tests for AppState's generated-client mapping.
/// Locks the local `AIDefaults` view model to the generated OpenAPI schemas
/// used by `fetchAIDefaults()`, `saveAIDefaults()`, and `resetAIDefaults()`.
@MainActor
final class AppStateAPIMappingTests: XCTestCase {

    // MARK: - Generated → Local

    func testMapGeneratedAIDefaultsToLocal() {
        let generated = Components.Schemas.AIDefaults(
            visionProvider: "vision-provider",
            visionModel: "vision-model",
            textProvider: "text-provider",
            textModel: "text-model",
            audioProvider: "audio-provider",
            audioModel: "audio-model",
            videoProvider: "video-provider",
            videoModel: "video-model",
            embeddingsProvider: "embeddings-provider",
            embeddingsModel: "embeddings-model",
            smallProvider: "small-provider",
            smallModel: "small-model",
            largeProvider: "large-provider",
            largeModel: "large-model",
            temperature: "0.7",
            maxTokens: "1024",
            promptPrefix: "prefix"
        )

        let local = AppState.map(generated)

        XCTAssertEqual(local.visionProvider, "vision-provider")
        XCTAssertEqual(local.visionModel, "vision-model")
        XCTAssertEqual(local.textProvider, "text-provider")
        XCTAssertEqual(local.textModel, "text-model")
        XCTAssertEqual(local.audioProvider, "audio-provider")
        XCTAssertEqual(local.audioModel, "audio-model")
        XCTAssertEqual(local.videoProvider, "video-provider")
        XCTAssertEqual(local.videoModel, "video-model")
        XCTAssertEqual(local.embeddingsProvider, "embeddings-provider")
        XCTAssertEqual(local.embeddingsModel, "embeddings-model")
        XCTAssertEqual(local.smallProvider, "small-provider")
        XCTAssertEqual(local.smallModel, "small-model")
        XCTAssertEqual(local.largeProvider, "large-provider")
        XCTAssertEqual(local.largeModel, "large-model")
        XCTAssertEqual(local.temperature, "0.7")
        XCTAssertEqual(local.maxTokens, "1024")
        XCTAssertEqual(local.promptPrefix, "prefix")
    }

    func testMapGeneratedAIDefaultsToLocalFallsBackToEmpty() {
        let generated = Components.Schemas.AIDefaults(textProvider: "text-provider")

        let local = AppState.map(generated)

        XCTAssertEqual(local.textProvider, "text-provider")
        XCTAssertEqual(local.visionProvider, "")
        XCTAssertEqual(local.temperature, "")
        XCTAssertEqual(local.promptPrefix, "")
    }

    // MARK: - Local → Update

    func testMapLocalAIDefaultsToUpdate() {
        var defaults = AIDefaults()
        defaults.visionProvider = "vision-provider"
        defaults.visionModel = "vision-model"
        defaults.textProvider = "text-provider"
        defaults.textModel = "text-model"
        defaults.smallProvider = "small-provider"
        defaults.smallModel = "small-model"
        defaults.temperature = "0.5"
        defaults.maxTokens = "512"
        defaults.promptPrefix = "helpful"

        let update = AppState.mapToUpdate(defaults)

        XCTAssertEqual(update.visionProvider, "vision-provider")
        XCTAssertEqual(update.visionModel, "vision-model")
        XCTAssertEqual(update.textProvider, "text-provider")
        XCTAssertEqual(update.textModel, "text-model")
        XCTAssertEqual(update.smallProvider, "small-provider")
        XCTAssertEqual(update.smallModel, "small-model")
        XCTAssertEqual(update.temperature, "0.5")
        XCTAssertEqual(update.maxTokens, "512")
        XCTAssertEqual(update.promptPrefix, "helpful")
        XCTAssertEqual(update.audioProvider, "")
        XCTAssertEqual(update.videoProvider, "")
        XCTAssertEqual(update.embeddingsProvider, "")
        XCTAssertEqual(update.largeProvider, "")
    }
}
