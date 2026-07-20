import FicheroAPIClient
import Foundation

extension AppState {
    func fetchAIDefaults() async throws -> AIDefaults {
        let response = try await ficheroClient.api.getAiDefaultsApiSettingsAiDefaultsGet(headers: .init())
        switch response {
        case .ok(let okResponse):
            let generated = try okResponse.body.json
            return AppState.map(generated)
        default:
            throw APIError.invalidResponse
        }
    }

    func saveAIDefaults(_ defaults: AIDefaults) async throws {
        let update = AppState.mapToUpdate(defaults)
        let response = try await ficheroClient.api.setAiDefaultsApiSettingsAiDefaultsPut(body: .json(update))
        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw APIError.httpError(statusCode: 422, message: detail?.detail?.description ?? "Validation error")
        default:
            throw APIError.invalidResponse
        }
    }

    func resetAIDefaults() async throws {
        let response = try await ficheroClient.api.resetAiDefaultsApiSettingsAiDefaultsDelete(headers: .init())
        switch response {
        case .ok:
            return
        default:
            throw APIError.invalidResponse
        }
    }

    /// Map generated OpenAPI AI defaults to the local view model.
    static func map(_ generated: Components.Schemas.AIDefaults) -> AIDefaults {
        AIDefaults(
            visionProvider: generated.visionProvider ?? "",
            visionModel: generated.visionModel ?? "",
            textProvider: generated.textProvider ?? "",
            textModel: generated.textModel ?? "",
            audioProvider: generated.audioProvider ?? "",
            audioModel: generated.audioModel ?? "",
            videoProvider: generated.videoProvider ?? "",
            videoModel: generated.videoModel ?? "",
            embeddingsProvider: generated.embeddingsProvider ?? "",
            embeddingsModel: generated.embeddingsModel ?? "",
            smallProvider: generated.smallProvider ?? "",
            smallModel: generated.smallModel ?? "",
            mediumProvider: generated.mediumProvider ?? "",
            mediumModel: generated.mediumModel ?? "",
            largeProvider: generated.largeProvider ?? "",
            largeModel: generated.largeModel ?? "",
            visionSmallProvider: generated.visionSmallProvider ?? "",
            visionSmallModel: generated.visionSmallModel ?? "",
            visionMediumProvider: generated.visionMediumProvider ?? "",
            visionMediumModel: generated.visionMediumModel ?? "",
            visionLargeProvider: generated.visionLargeProvider ?? "",
            visionLargeModel: generated.visionLargeModel ?? "",
            temperature: generated.temperature ?? "",
            maxTokens: generated.maxTokens ?? "",
            promptPrefix: generated.promptPrefix ?? "",
            primaryLanguage: generated.primaryLanguage ?? ""
        )
    }

    /// Map the local AI defaults view model to the generated update payload.
    static func mapToUpdate(_ defaults: AIDefaults) -> Components.Schemas.AIDefaultsUpdate {
        Components.Schemas.AIDefaultsUpdate(
            visionProvider: defaults.visionProvider,
            visionModel: defaults.visionModel,
            textProvider: defaults.textProvider,
            textModel: defaults.textModel,
            audioProvider: defaults.audioProvider,
            audioModel: defaults.audioModel,
            videoProvider: defaults.videoProvider,
            videoModel: defaults.videoModel,
            embeddingsProvider: defaults.embeddingsProvider,
            embeddingsModel: defaults.embeddingsModel,
            smallProvider: defaults.smallProvider,
            smallModel: defaults.smallModel,
            mediumProvider: defaults.mediumProvider,
            mediumModel: defaults.mediumModel,
            largeProvider: defaults.largeProvider,
            largeModel: defaults.largeModel,
            visionSmallProvider: defaults.visionSmallProvider,
            visionSmallModel: defaults.visionSmallModel,
            visionMediumProvider: defaults.visionMediumProvider,
            visionMediumModel: defaults.visionMediumModel,
            visionLargeProvider: defaults.visionLargeProvider,
            visionLargeModel: defaults.visionLargeModel,
            primaryLanguage: defaults.primaryLanguage,
            temperature: defaults.temperature,
            maxTokens: defaults.maxTokens,
            promptPrefix: defaults.promptPrefix
        )
    }
}
