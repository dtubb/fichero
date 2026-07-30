import Foundation

/// How much precision a model's self-reported confidence can honestly carry
/// (#4394).
///
/// A claim badge read `0.70`. Tracing it back through
/// `workflows/tools/extractors.py`, the value is a number the LLM emitted
/// alongside the claim — not a measurement of whether the claim is true. Two
/// decimal places assert a precision that does not exist: 0.70 against 0.65 is
/// not a difference a user can act on, and the badge sits in the most crowded
/// part of the inspector where it competes with facts that ARE measured.
///
/// A band is the most the underlying signal supports. It reads at a glance,
/// it cannot be mistaken for a measurement, and it degrades honestly when the
/// model's number is noise.
///
/// This deliberately does NOT invent precision it lacks in the other
/// direction either — there is no "very high", because the signal cannot
/// distinguish one.
///
/// **What this cannot fix.** `extractors.py` writes `0.5` when the model said
/// nothing or said something unparseable, so "the model was unsure" and "the
/// model was silent" arrive at the client already collapsed into one value.
/// No client rendering can separate them; the engine has to stop substituting.
/// Reported on #4394 rather than papered over here.
enum ConfidenceBand: String, CaseIterable {
    case low
    case medium
    case high

    /// Boundaries are deliberately coarse and round. They are not tuned,
    /// because there is nothing to tune against — an uncalibrated self-report
    /// has no ground truth to fit. Their only job is to stop the UI implying
    /// two-decimal precision.
    static func band(for value: Double) -> ConfidenceBand {
        let clamped = max(0, min(1, value))
        if clamped < 0.4 { return .low }
        if clamped < 0.75 { return .medium }
        return .high
    }

    /// Short form for a lozenge. Prefixed by the caller with what it measures —
    /// a bare word is as unreadable as a bare number.
    var short: String {
        switch self {
        case .low: return "low"
        case .medium: return "med"
        case .high: return "high"
        }
    }

    /// Full form for tooltips and accessibility.
    var label: String {
        switch self {
        case .low: return "Low"
        case .medium: return "Medium"
        case .high: return "High"
        }
    }

    /// What the badge says on screen: always labelled, never a bare value.
    ///
    /// The original badge was a naked `0.70` in a capsule, which could have
    /// been a score, a page, a version or a weight — the issue's first
    /// complaint, and true of every unlabelled number in a dense row.
    var badgeText: String { "conf \(short)" }

    /// The tooltip, which is where the honesty about provenance belongs.
    ///
    /// Says what the number IS, not just what it is called. A user deciding
    /// whether to trust or delete a claim needs to know this is the model's
    /// own estimate.
    var help: String {
        "\(label) confidence — the extracting model's own estimate, not a measurement"
    }
}
