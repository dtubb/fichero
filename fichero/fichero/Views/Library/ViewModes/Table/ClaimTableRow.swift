import FicheroAPIClient
import Foundation

/// The display values for one claim row in the claims table view — the node-model
/// build where a claim flows through the SAME library table as a document.
///
/// A pure value mapping over `KnowledgeClaim`: no UI, no async, `nonisolated` so
/// the column contents are testable off-main (the macOS-26 View-static MainActor
/// SIGTRAP hazard) and every claim column reads from ONE source of truth. It
/// reuses the same typed SVO fields `ClaimSummaryCard.svoTriple` reads and the
/// same confidence/curation honesty rules the inspector already enforces —
/// nothing here invents precision a claim did not record.
struct ClaimTableRow: Equatable, Sendable {
    var subject: String
    var verb: String
    var object: String
    /// The claim's own date — its temporal context, else a recorded start time.
    /// Empty when the claim carries no date (never a fabricated one).
    var date: String
    /// Source page label, normalized to "p. N". Empty when unrecorded.
    var sourcePage: String
    /// Confidence BAND text ("Low"/"Medium"/"High"), or empty when no confidence
    /// was recorded — absence is not a value (ConfidenceBand.recorded).
    var confidence: String
    /// Where the claim came from / how far it has been curated.
    var provenance: Provenance

    /// The row's honesty axis. A human-approved claim is "Blessed"; a rejected one
    /// says so; otherwise it reads as the extractor that produced it (an LLM, or a
    /// heuristic default) — never dressed up as more than it is.
    enum Provenance: String, Equatable, Sendable {
        case blessed = "Blessed"
        case human = "Human"
        case llm = "LLM"
        case heuristic = "Heuristic"
        case rejected = "Rejected"
        case unknown = "—"
    }

    init(_ claim: Components.Schemas.KnowledgeClaim) {
        self.subject = Self.clean(claim.subjectCanonical)
        self.verb = Self.clean(claim.predicateVerb)
        self.object = Self.clean(claim.objectPhrase)
        self.date = Self.dateText(claim)
        self.sourcePage = Self.pageText(claim.sourcePageLabel)
        self.confidence = ConfidenceBand.recorded(claim.confidence)?.label ?? ""
        self.provenance = Self.provenance(claim)
    }

    /// The SVO as one line, for a single-column fallback or accessibility — reuses
    /// ClaimLine so the sentence reads the same as everywhere else. `groupSubject`
    /// is nil here: a claims table is not grouped under one entity, so the subject
    /// stays.
    var svoLine: String {
        ClaimLine.text(subject: subject, verb: verb, object: object, fallback: "", groupSubject: nil)
    }

    // MARK: - Field derivation (pure)

    static func dateText(_ claim: Components.Schemas.KnowledgeClaim) -> String {
        let temporal = clean(claim.temporalContext)
        if !temporal.isEmpty, temporal.lowercased() != "unknown" { return temporal }
        let start = clean(claim.timeStart)
        return start.lowercased() == "unknown" ? "" : start
    }

    static func pageText(_ rawLabel: String?) -> String {
        let label = clean(rawLabel)
        guard !label.isEmpty else { return "" }
        return label.lowercased().hasPrefix("p.") ? label : "p. \(label)"
    }

    /// Curation wins over origin: an approved claim is "Blessed", a rejected one
    /// "Rejected" — those are decisions a human made. Only an un-curated claim
    /// falls back to WHO extracted it, classified from `confidence_source`.
    static func provenance(_ claim: Components.Schemas.KnowledgeClaim) -> Provenance {
        switch claim.curationState {
        case .some(.curated): return .blessed
        case .some(.rejected): return .rejected
        default: break  // shortlisted / unreviewed / no curation state → fall to origin
        }
        let meta = claim.metadata?.additionalProperties.value
        let raw = clean(
            claim.confidenceSource
                ?? (meta?["confidence_source"] as? String)
                ?? (meta?["confidenceSource"] as? String)
        ).lowercased()
        switch raw {
        case "human_review", "human", "manual", "user", "curator", "editor", "researcher":
            return .human
        case "llm_logprob", "llm", "ai", "agent":
            return .llm
        case "heuristic", "default", "corroboration":
            return .heuristic
        case "":
            return .unknown
        default:
            // An unrecognised but present source is an extractor we don't have a
            // friendly name for — honest "LLM" beats inventing a category, since
            // every non-heuristic, non-human source in the pipeline is a model.
            return .llm
        }
    }

    private static func clean(_ value: String?) -> String {
        (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
