import FicheroAPIClient
import SwiftUI

// MARK: - Prediction Review State

@MainActor
final class PredictionReviewState: ObservableObject {
    @Published var predictionRuns: [Components.Schemas.KnowledgePredictionRun] = []
    @Published var selectedRun: Components.Schemas.KnowledgePredictionRun?
    @Published var isLoading = false
    @Published var isGenerating = false
    @Published var isApplying = false
    @Published var loadError: String?
    @Published var applyResult: ApplyResult?
    @Published var runPredictions: [Components.Schemas.KnowledgePrediction] = []

    struct ApplyResult: Identifiable {
        let id = UUID()
        let success: Bool
        let message: String
    }

    func loadPredictionRuns() async {
        isLoading = true
        loadError = nil

        do {
            let library = LibraryManager.shared.globalLibrary
            let service = KnowledgeGraphServiceGenerated(apiClient: library!.apiClient)
            predictionRuns = try await service.listPredictions(limit: 20)
        } catch {
            loadError = error.localizedDescription
        }

        isLoading = false
    }

    func generatePredictions() async {
        isGenerating = true
        loadError = nil

        do {
            let library = LibraryManager.shared.globalLibrary
            let service = KnowledgeGraphServiceGenerated(apiClient: library!.apiClient)
            let newRun = try await service.generateHeuristicPredictions()
            predictionRuns.insert(newRun, at: 0)
            selectedRun = newRun
        } catch {
            loadError = "Generation failed: \(error.localizedDescription)"
        }

        isGenerating = false
    }

    func applyPredictions(_ run: Components.Schemas.KnowledgePredictionRun) async {
        guard let runId = run.id else { return }

        isApplying = true

        do {
            let library = LibraryManager.shared.globalLibrary
            let service = KnowledgeGraphServiceGenerated(apiClient: library!.apiClient)
            try await service.applyPredictions(runId: runId)
            applyResult = ApplyResult(success: true, message: "Predictions applied successfully")
        } catch {
            applyResult = ApplyResult(success: false, message: "Apply failed: \(error.localizedDescription)")
        }

        isApplying = false
    }
}
