import Foundation
import OSLog

extension ComparisonDetailView {

    // MARK: - Helpers

    func formatLatency(_ ms: Double) -> String {
        if ms < 1000 {
            return String(format: "%.0fms", ms)
        } else {
            return String(format: "%.1fs", ms / 1000)
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

        do {
            let url = URL(string: "http://localhost:8765/api/model-comparison/comparison/\(comparisonSummary.comparisonId)")!
            let (data, response) = try await URLSession.shared.data(from: url)

            guard let httpResponse = response as? HTTPURLResponse else {
                throw URLError(.badServerResponse)
            }

            if httpResponse.statusCode == 404 {
                self.error = "Comparison not found"
            } else if httpResponse.statusCode != 200 {
                self.error = "Server error: \(httpResponse.statusCode)"
            } else {
                let decoder = JSONDecoder()
                comparison = try decoder.decode(ComparisonDetail.self, from: data)
            }
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func rerunComparison(_ comparison: ComparisonDetail) async {
        comparisonDetailLogger.info("Re-running comparison with prompt: \(comparison.prompt.prefix(50))")
        // In the future, this would trigger a new comparison with the same settings
    }
}
