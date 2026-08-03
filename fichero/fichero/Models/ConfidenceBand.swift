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
/// **Absence is not a value.** A confidence that was never recorded renders as
/// nothing — `recorded(_:)` below is the seam that makes that a property a test
/// can hold, rather than an `if let` that any later edit can turn into
/// `?? 0.5`.
///
/// **What this still cannot fix.** `extractors.py` writes `0.5` when the model
/// said nothing or said something unparseable, so for claims from that path
/// "the model was unsure" and "the model was silent" arrive at the client
/// already collapsed into one value. Nothing on this side can separate them;
/// the engine has to stop substituting. Reported on #4394 rather than papered
/// over here — a client-side guess at which 0.5 was real would be the same
/// dishonesty one layer up.
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

    /// The band for a confidence that MAY NOT EXIST — `nil` in, `nil` out.
    ///
    /// "No confidence was recorded" and "the model said 0.5" are different
    /// facts, and a historian deciding whether to trust a claim would act
    /// differently on each. Absence renders as NOTHING: no badge, no
    /// placeholder, no substituted midpoint. A half-working affordance that
    /// shows a number for a value nobody produced is worse than no affordance,
    /// because the user cannot tell it apart from one that was.
    ///
    /// This exists as a function, rather than as an `if let` repeated at each
    /// call site, so the distinction is a thing a test can hold. The failure
    /// mode being fenced off is a future `confidence ?? 0.5` — which looks
    /// tidy, compiles, renders a badge on every row, and quietly asserts a
    /// measurement that was never taken. `ConfidenceBandTests` fails if
    /// absent and 0.5 ever render the same.
    static func recorded(_ value: Double?) -> ConfidenceBand? {
        value.map(band(for:))
    }

    /// Order two possibly-absent confidences, or `nil` when the caller's own
    /// tiebreak should decide.
    ///
    /// The same distinction, in ranking rather than rendering. Sorting with
    /// `confidence ?? 0` reads as harmless and is the identical silent
    /// substitution: it ranks a claim nobody scored exactly where it ranks a
    /// claim the model scored 0.0 — "we don't know" presented as "we know it
    /// is worthless", and the two then interleave under the name tiebreak so
    /// they cannot even be told apart by position.
    ///
    /// Unrecorded sorts after every recorded value. That is not a claim that
    /// it is the weakest; it is a claim that it cannot be ranked, so it leaves
    /// the ranking rather than being given a number to sit at.
    static func ordersBefore(_ lhs: Double?, _ rhs: Double?) -> Bool? {
        switch (lhs, rhs) {
        case let (left?, right?):
            return left == right ? nil : left > right
        case (nil, .some):
            return false
        case (.some, nil):
            return true
        case (nil, nil):
            return nil
        }
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
