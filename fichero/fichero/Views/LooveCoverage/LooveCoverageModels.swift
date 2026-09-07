import SwiftUI

// MARK: - loove coverage domain model
//
// Plain Swift value types the coverage window renders. `LooveCoverageService`
// maps the generated OpenAPI response (`Components.Schemas.LanguageCoverageRecord`
// et al.) into these, so the view layer never touches generator-named types and
// the matrix stays honest about missing data — a `nil` score renders "—", never a
// fabricated number.

/// Qualitative coverage band from the engine's `score_band` enum. `.unknown`
/// absorbs a missing / unrecognized band so the UI always has a color to show.
enum CoverageBand: String, CaseIterable, Sendable {
    case excellent
    case good
    case limited
    case poor
    case unknown

    /// Map the generated string enum's raw value (or `nil`) onto a band.
    init(rawBand: String?) {
        self = CoverageBand(rawValue: rawBand ?? "") ?? .unknown
    }

    /// Semantic color for the band. Green→blue→orange→red descending quality;
    /// gray for unknown. Used for the score text and the header legend.
    var color: Color {
        switch self {
        case .excellent: return .green
        case .good: return .blue
        case .limited: return .orange
        case .poor: return .red
        case .unknown: return .secondary
        }
    }

    var label: String {
        switch self {
        case .excellent: return "Excellent"
        case .good: return "Good"
        case .limited: return "Limited"
        case .poor: return "Poor"
        case .unknown: return "Unknown"
        }
    }
}

/// The four LOOVE tokenizer tiers — how a script's characters are reachable by a
/// model's tokenizer. Tier 0 is best (native single-char tokens), Tier 3 worst
/// (unreachable). Drives the 4-segment bar in every cell and the legend.
enum CoverageTier: Int, CaseIterable, Sendable {
    case native = 0        // Tier 0 — native single-character tokens
    case embedded = 1      // Tier 1 — embedded in multi-character tokens
    case byteFallback = 2  // Tier 2 — byte-fallback tokens
    case unreachable = 3   // Tier 3 — not reachable by the tokenizer

    var color: Color {
        switch self {
        case .native: return .green
        case .embedded: return .teal
        case .byteFallback: return .orange
        case .unreachable: return .red
        }
    }

    var shortLabel: String {
        switch self {
        case .native: return "Tier 0 · native"
        case .embedded: return "Tier 1 · embedded"
        case .byteFallback: return "Tier 2 · byte"
        case .unreachable: return "Tier 3 · unreachable"
        }
    }
}

/// Per-cell tier counts (exemplar-character histogram). `count(for:)` lets the
/// bar iterate `CoverageTier.allCases` without a switch at each call site.
struct CoverageTierCounts: Equatable, Sendable {
    var native: Int
    var embedded: Int
    var byteFallback: Int
    var unreachable: Int

    var total: Int { native + embedded + byteFallback + unreachable }
    var isEmpty: Bool { total == 0 }

    func count(for tier: CoverageTier) -> Int {
        switch tier {
        case .native: return native
        case .embedded: return embedded
        case .byteFallback: return byteFallback
        case .unreachable: return unreachable
        }
    }
}

/// How much to trust a cell's number. THE honesty axis of this window — a tool
/// about tokenizer coverage must never present a per-script guess as a
/// measurement.
///
/// - `derived`: real tokenizer-derived coverage (`source.kind ==
///   loove_derived_json`, `status == derived`). Full confidence — band color.
/// - `heuristic`: the engine's model-independent per-SCRIPT fallback guess
///   (`heuristic_fallback`). Rendered muted with a "~"/"est." marker, NEVER the
///   confident band color.
/// - `unknown`: no score, or no tokenizer to measure (e.g. Apple), or
///   `source.kind == missing`. Rendered "—".
enum CoverageConfidence: Sendable {
    case derived
    case heuristic
    case unknown
}

/// One (model × language) coverage result. `coverageScore == nil` and
/// `tierCounts == nil` are legitimate ("we have no derived data yet") and render
/// as "—".
struct CoverageCell: Identifiable, Equatable, Sendable {
    var provider: String
    var model: String
    var coverageScore: Double?
    var band: CoverageBand
    var tierCounts: CoverageTierCounts?
    var tokensPerChar: Double?
    /// Raw engine status: `derived` / `heuristic` / `unsupported_language` /
    /// `invalid_coverage_file`. Feeds `confidence` and the cell tooltip.
    var status: String
    /// Raw `source.kind`: `loove_derived_json` / `heuristic_fallback` / `missing`.
    /// The authority for whether the score was measured or guessed.
    var sourceKind: String

    var id: String { "\(provider)/\(model)" }

    /// Whether the number was MEASURED, GUESSED, or is absent. `source.kind` is
    /// the authority; a nil score is always unknown regardless of status.
    var confidence: CoverageConfidence {
        guard coverageScore != nil else { return .unknown }
        switch sourceKind {
        case "loove_derived_json":
            // Only a `derived` status confirms the measurement; any other status
            // on a derived file (e.g. invalid) drops to a guess, never full trust.
            return status == "derived" ? .derived : .heuristic
        case "heuristic_fallback":
            return .heuristic
        default: // "missing" or anything unrecognized
            return .unknown
        }
    }
}

/// A language column in the matrix.
struct CoverageLanguage: Identifiable, Equatable, Sendable {
    var code: String
    var name: String

    var id: String { code }
}

/// A model row: its cells keyed by language code. A language with no record for
/// this model simply has no entry — the view shows "—" there.
struct CoverageModelRow: Identifiable, Equatable, Sendable {
    var provider: String
    var model: String
    var cellsByLanguage: [String: CoverageCell]

    var id: String { "\(provider)/\(model)" }
}

/// The assembled matrix: languages (columns) × model rows.
struct CoverageMatrix: Equatable, Sendable {
    var languages: [CoverageLanguage]
    var rows: [CoverageModelRow]

    var isEmpty: Bool { rows.isEmpty }
}
