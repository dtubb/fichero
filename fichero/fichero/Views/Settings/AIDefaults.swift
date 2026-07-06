import Foundation

// MARK: - AI Defaults Model

/// Default AI model configuration per category.
/// Matches the Python AIDefaults Pydantic model.
struct AIDefaults: Codable, Equatable {
    var visionProvider: String = ""
    var visionModel: String = ""
    var textProvider: String = ""
    var textModel: String = ""
    var audioProvider: String = ""
    var audioModel: String = ""
    var videoProvider: String = ""
    var videoModel: String = ""
    var embeddingsProvider: String = ""
    var embeddingsModel: String = ""
    // Capability-tier defaults referenced by workflow nodes via the
    // $small / $medium / $large model aliases (#810/#813).
    var smallProvider: String = ""
    var smallModel: String = ""
    var mediumProvider: String = ""
    var mediumModel: String = ""
    var largeProvider: String = ""
    var largeModel: String = ""
    // Vision-capability tier aliases ($vision_small / $vision_medium /
    // $vision_large, #2200) — the fallback targets vision workflow nodes
    // reference. Mirrors the backend's vision_* tier surface so `$vision_medium`
    // resolves to a user-set model instead of a silent dead end (#3220).
    var visionSmallProvider: String = ""
    var visionSmallModel: String = ""
    var visionMediumProvider: String = ""
    var visionMediumModel: String = ""
    var visionLargeProvider: String = ""
    var visionLargeModel: String = ""
    var temperature: String = ""
    var maxTokens: String = ""
    var promptPrefix: String = ""
    /// Forces extraction into this language regardless of the source's own
    /// language (empty = Auto / detect per source). Honored by the backend's
    /// default_primary_language (#1764) — this exposes the previously
    /// unreachable control (#1808).
    var primaryLanguage: String = ""

    enum CodingKeys: String, CodingKey {
        case visionProvider = "vision_provider"
        case visionModel = "vision_model"
        case textProvider = "text_provider"
        case textModel = "text_model"
        case audioProvider = "audio_provider"
        case audioModel = "audio_model"
        case videoProvider = "video_provider"
        case videoModel = "video_model"
        case embeddingsProvider = "embeddings_provider"
        case embeddingsModel = "embeddings_model"
        case smallProvider = "small_provider"
        case smallModel = "small_model"
        case mediumProvider = "medium_provider"
        case mediumModel = "medium_model"
        case largeProvider = "large_provider"
        case largeModel = "large_model"
        case visionSmallProvider = "vision_small_provider"
        case visionSmallModel = "vision_small_model"
        case visionMediumProvider = "vision_medium_provider"
        case visionMediumModel = "vision_medium_model"
        case visionLargeProvider = "vision_large_provider"
        case visionLargeModel = "vision_large_model"
        case temperature
        case maxTokens = "max_tokens"
        case promptPrefix = "prompt_prefix"
        case primaryLanguage = "primary_language"
    }

    /// First-launch seed for Apple Intelligence defaults. Only fills empty
    /// slots so existing user choices remain untouched.
    mutating func seedAppleDefaultsIfNeeded(appleAvailable: Bool) {
        guard appleAvailable else { return }

        if textProvider.isEmpty { textProvider = "apple" }
        if textProvider == "apple", textModel.isEmpty { textModel = "apple-intelligence" }

        if visionProvider.isEmpty { visionProvider = "apple" }
        if visionProvider == "apple", visionModel.isEmpty { visionModel = "apple-vision" }

        if audioProvider.isEmpty { audioProvider = "apple" }
        if audioProvider == "apple", audioModel.isEmpty { audioModel = "apple-speech" }

        if smallProvider.isEmpty { smallProvider = "apple" }
        if smallProvider == "apple", smallModel.isEmpty { smallModel = "apple-intelligence" }

        if largeProvider.isEmpty { largeProvider = "apple" }
        if largeProvider == "apple", largeModel.isEmpty { largeModel = "apple-intelligence" }
    }
}
