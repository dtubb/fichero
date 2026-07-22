import FicheroAPIClient
import Foundation
import OSLog

extension ComparisonDetailView {

    // MARK: - Helpers

    func formatLatency(_ milliseconds: Double) -> String {
        if milliseconds < 1000 {
            return String(format: "%.0fms", milliseconds)
        } else {
            return String(format: "%.1fs", milliseconds / 1000)
        }
    }

    func formatModelName(_ model: String) -> String {
        // Shorten long model names
        if model.count > 20 {
            return String(model.prefix(17)) + "..."
        }
        return model
    }

    // MARK: - Actions

    func loadComparison() async {
        isLoading = true
        error = nil

        // Route through the generated client (injects auth + library header)
        // instead of a hand-written URLSession call. Model-comparison is a
        // dev-tier, app-wide feature; the middleware still supplies the bearer
        // token the backend requires.
        let client = libraryManager.globalLibrary?.ficheroClient ?? FicheroClient(baseURL: EngineConfig.host, transportMode: EngineConfig.transportMode)

        do {
            let response = try await client.api.getComparisonApiModelComparisonComparisonComparisonIdGet(
                path: .init(comparisonId: comparisonSummary.comparisonId)
            )

            switch response {
            case .ok(let okResponse):
                comparison = Self.mapComparison(try okResponse.body.json)
            case .unprocessableContent:
                self.error = "Comparison not found"
            case .undocumented(let statusCode, _):
                self.error = "Server error: \(statusCode)"
            }
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    /// Map the generated `ComparisonResultResponse` to the app's `ComparisonDetail`.
    private static func mapComparison(
        _ response: Components.Schemas.ComparisonResultResponse
    ) -> ComparisonDetail {
        let results = response.results.map { result in
            ModelResultDetail(
                provider: result.provider,
                model: result.model,
                response: result.response,
                latencyMs: result.latencyMs,
                inputTokens: result.inputTokens,
                outputTokens: result.outputTokens,
                costUsd: result.costUsd,
                error: result.error,
                timestamp: result.timestamp
            )
        }

        return ComparisonDetail(
            prompt: response.prompt,
            modelsCompared: response.modelsCompared,
            results: results,
            fastestModel: response.fastestModel,
            cheapestModel: response.cheapestModel,
            totalCostUsd: response.totalCostUsd,
            totalLatencyMs: response.totalLatencyMs,
            comparisonId: response.comparisonId,
            timestamp: response.timestamp
        )
    }

    func rerunComparison(_ comparison: ComparisonDetail) async {
        comparisonDetailLogger.info("Re-running comparison with prompt: \(comparison.prompt.prefix(50))")
        // In the future, this would trigger a new comparison with the same settings
    }
}
