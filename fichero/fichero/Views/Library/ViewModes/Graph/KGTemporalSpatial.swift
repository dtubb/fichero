import FicheroAPIClient
import SwiftUI

// Shared temporal + spatial helpers for the Knowledge Graph Timeline and
// Map views (#1267). Centralising three things keeps the two new views
// visually consistent with `ForceDirectedGraphView` / `EntityKindChartView`:
//
//   1. flexible ISO-8601 date parsing (year / month / day / full timestamp),
//   2. the asserted-vs-inferred *provenance* classifier, and
//   3. the entity-kind colour palette.
//
// The backend temporal/spatial fields land via #1266; every accessor here
// is nil-tolerant, so when a claim hasn't been enriched yet the views fall
// back to an empty state rather than crashing. Nothing here assumes a field
// is populated — it only reads `Components.Schemas.KnowledgeClaim` optionals.

/// How trustworthy a claim's date / place is. Drives the visual treatment
/// (solid vs hollow/dim) so a researcher can tell a date explicitly stated
/// in the source from one the extractor inferred or approximated.
enum KGProvenance: String, CaseIterable, Identifiable {
    /// Explicitly stated in the source and precisely grounded.
    case asserted
    /// Derived / approximate — fuzzy precision, relative phrasing, or a
    /// low-trust confidence source.
    case inferred

    var id: String { rawValue }

    var label: String {
        switch self {
        case .asserted: return "Asserted"
        case .inferred: return "Inferred"
        }
    }
}

/// Temporal helpers — date parsing + the date-provenance classifier.
enum KGTemporal {
    /// Parse a partial or full ISO-8601 date string into a `Date` anchored
    /// at the *start* of the period it denotes:
    ///   "1820"        → 1820-01-01
    ///   "1820-05"     → 1820-05-01
    ///   "1820-05-13"  → 1820-05-13
    ///   "1820-05-13T…"→ full timestamp
    /// Returns nil for empty, "unknown", or unparseable input. BCE / negative
    /// years are out of scope (returns nil) — historical edge case, handled
    /// gracefully rather than guessed.
    static func parseFlexibleDate(_ raw: String?) -> Date? {
        guard let trimmed = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty,
              trimmed.lowercased() != "unknown" else { return nil }

        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC") ?? .current

        // Date portion before any time separator ("T" or space).
        let datePart = trimmed.split(whereSeparator: { $0 == "T" || $0 == " " })
            .first.map(String.init) ?? trimmed
        let pieces = datePart.split(separator: "-", omittingEmptySubsequences: false).map { Int($0) }

        guard let first = pieces.first, let year = first, year > 0 else {
            // Not "YYYY-…" — try a full ISO-8601 timestamp parse as a fallback.
            return ISO8601DateFormatter().date(from: trimmed)
        }
        var components = DateComponents()
        components.year = year
        components.month = pieces.count > 1 ? (pieces[1] ?? 1) : 1
        components.day = pieces.count > 2 ? (pieces[2] ?? 1) : 1
        return calendar.date(from: components)
    }

    /// Classify how grounded a claim's *date* is. Asserted = a present
    /// `timeStart` with day/month/year precision and a trustworthy
    /// confidence source; inferred = fuzzy precision ("range"/"unknown"),
    /// a missing start, or a low-trust confidence origin.
    ///
    /// `timePrecision` vocabulary: 'year' | 'month' | 'day' | 'range' | 'unknown'.
    /// `confidenceSource` vocabulary: 'llm_logprob' | 'heuristic' |
    /// 'human_review' | 'corroboration' | 'default'.
    static func provenance(for claim: Components.Schemas.KnowledgeClaim) -> KGProvenance {
        guard claim.timeStart != nil else { return .inferred }
        let precision = (claim.timePrecision ?? "").lowercased()
        if precision == "unknown" || precision == "range" { return .inferred }
        let source = (claim.confidenceSource ?? "").lowercased()
        if source == "heuristic" || source == "default" { return .inferred }
        return .asserted
    }
}

/// Spatial helpers — the place-provenance classifier.
enum KGSpatial {
    /// Classify how grounded a claim's *location* is. Asserted = a precise
    /// geocoded fix; inferred = a coarse radius (`precisionM` > 50 km) or a
    /// low-trust confidence origin. A claim with only `claimLocation` text
    /// and no `claimGeo` is treated as inferred (it can't be mapped).
    static func provenance(for claim: Components.Schemas.KnowledgeClaim) -> KGProvenance {
        guard let geo = claim.claimGeo else { return .inferred }
        if let precision = geo.precisionM, precision > 50_000 { return .inferred }
        let source = (claim.confidenceSource ?? "").lowercased()
        if source == "heuristic" || source == "default" { return .inferred }
        return .asserted
    }
}

extension Components.Schemas.EntityTypeOutput {
    /// Shared kind→colour palette. Mirrors `ForceDirectedGraphView.color(for:)`
    /// and `EntityKindChartView.color(for:)` so a glance across Graph, Chart,
    /// Timeline, and Map lands on the same colour for the same kind.
    var kgColor: Color {
        switch self {
        case .person: return .blue
        case .organization: return .purple
        case .location: return .green
        case .event: return .orange
        case .concept: return .yellow
        case .citation: return .brown
        case .other: return .gray
        }
    }
}

/// Colour for an optional kind — defaults to gray for `nil` (e.g. a claim
/// whose subject didn't resolve to a typed entity).
func kgEntityColor(for kind: Components.Schemas.EntityTypeOutput?) -> Color {
    kind?.kgColor ?? .gray
}
