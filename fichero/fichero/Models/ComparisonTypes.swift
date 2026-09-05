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
    /// Nil when nothing in the comparison could be priced (2026-09-03). Not
    /// zero: a zero here read as "this comparison was free", about calls that
    /// billed.
    let totalCostUsd: Double?
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

/// How a cost renders when it may not exist.
///
/// One helper, used by every comparison surface, so no view has to decide on
/// its own what to print for a missing price — the decision that produced
/// "$0.0000" for models nobody has a price for.
enum CostDisplay {
    /// "$0.0042", "Free", or "Unpriced". Never a zero standing in for unknown.
    static func text(_ value: Double?, decimals: Int = 4) -> String {
        guard let value else { return "Unpriced" }
        if value == 0 { return "Free" }
        return String(format: "$%.\(decimals)f", value)
    }

    /// Secondary/orange styling cue: an unpriced cost is not an ordinary value.
    static func isKnown(_ value: Double?) -> Bool { value != nil }
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
