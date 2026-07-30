import Foundation

/// Summary of a comparison for sidebar + detail display.
///
/// Backend response type from `/comparisons` endpoints — used by
/// `ComparisonDetailView` and sidebar models. Previously defined inline
/// in `ChatSidebarContent.swift` (now deleted along with the rest of
/// the pre-unified mode-sidebar era).
struct ComparisonSummary: Codable, Identifiable, Equatable, Hashable {
    var id: String { comparisonId }
    let prompt: String
    let modelsCompared: [String]
    let totalCostUsd: Double
    let comparisonId: String
    let timestamp: String

    enum CodingKeys: String, CodingKey {
        case prompt
        case modelsCompared = "models_compared"
        case totalCostUsd = "total_cost_usd"
        case comparisonId = "comparison_id"
        case timestamp
    }
}

struct ComparisonHistoryResponse: Codable {
    let history: [ComparisonSummary]
}

extension ComparisonSummary {
    /// Sidebar-row projection of a full comparison result (#4335). The
    /// history endpoint returns full `ComparisonResultResponse` rows; the
    /// sidebar bucket needs only the summary fields.
    init(_ result: ComparisonResult) {
        self.init(
            prompt: result.prompt,
            modelsCompared: result.modelsCompared,
            totalCostUsd: result.totalCostUsd,
            comparisonId: result.comparisonId,
            timestamp: result.timestamp
        )
    }
}
