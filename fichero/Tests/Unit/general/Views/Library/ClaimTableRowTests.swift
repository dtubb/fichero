@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The claims table view renders a claim as a row of columns (subject · verb ·
/// object · date · source page · confidence · provenance). `ClaimTableRow` is the
/// pure mapping behind those columns; these tests pin it, including the honesty
/// rules (absence is not a value; curation wins over origin).
struct ClaimTableRowTests {

    private func claim(
        subject: String? = "Adolfo Hurtado",
        verb: String? = "compareció",
        object: String? = "ante el notario",
        temporal: String? = nil,
        timeStart: String? = nil,
        page: String? = "4",
        confidence: Double? = nil,
        confidenceSource: String? = nil,
        curation: Components.Schemas.ClaimCurationState? = nil
    ) -> Components.Schemas.KnowledgeClaim {
        // Argument order follows the generated struct's property declaration
        // order (openapi.json): a memberwise init is positional even when labeled.
        Components.Schemas.KnowledgeClaim(
            id: "claim-1",
            text: "\(subject ?? "") \(verb ?? "") \(object ?? "")",
            sourcePageLabel: page,
            timeStart: timeStart,
            subjectCanonical: subject,
            predicateVerb: verb,
            objectPhrase: object,
            curationState: curation,
            confidence: confidence,
            temporalContext: temporal,
            confidenceSource: confidenceSource
        )
    }

    @Test("subject / verb / object map straight through")
    func svoMapsThrough() {
        let row = ClaimTableRow(claim())
        #expect(row.subject == "Adolfo Hurtado")
        #expect(row.verb == "compareció")
        #expect(row.object == "ante el notario")
    }

    @Test("date prefers temporal context, then a recorded start, else empty")
    func dateResolution() {
        #expect(ClaimTableRow(claim(temporal: "1859", timeStart: "1860")).date == "1859")
        #expect(ClaimTableRow(claim(temporal: nil, timeStart: "1860-01-29")).date == "1860-01-29")
        #expect(ClaimTableRow(claim(temporal: nil, timeStart: nil)).date == "")
        // "unknown" is not a date — it must not render as one.
        #expect(ClaimTableRow(claim(temporal: "unknown", timeStart: nil)).date == "")
    }

    @Test("source page normalizes to p. N and stays empty when unrecorded")
    func pageNormalization() {
        #expect(ClaimTableRow(claim(page: "4")).sourcePage == "p. 4")
        #expect(ClaimTableRow(claim(page: "p. 12")).sourcePage == "p. 12")
        #expect(ClaimTableRow(claim(page: nil)).sourcePage == "")
    }

    @Test("confidence is a band, and absence renders as nothing — never 0.5")
    func confidenceBandOrNothing() {
        #expect(ClaimTableRow(claim(confidence: 0.92)).confidence == "High")
        #expect(ClaimTableRow(claim(confidence: 0.5)).confidence == "Medium")
        #expect(ClaimTableRow(claim(confidence: 0.2)).confidence == "Low")
        // The honesty rule: a claim with no recorded confidence shows no band.
        #expect(ClaimTableRow(claim(confidence: nil)).confidence == "")
    }

    @Test("curation wins over origin — approved is Blessed, rejected is Rejected")
    func curationWins() {
        #expect(ClaimTableRow(claim(confidenceSource: "llm", curation: .curated)).provenance == .blessed)
        #expect(ClaimTableRow(claim(confidenceSource: "llm", curation: .rejected)).provenance == .rejected)
    }

    @Test("an un-curated claim reads as its extractor")
    func provenanceFromSource() {
        #expect(ClaimTableRow(claim(confidenceSource: "llm_logprob")).provenance == .llm)
        #expect(ClaimTableRow(claim(confidenceSource: "heuristic")).provenance == .heuristic)
        #expect(ClaimTableRow(claim(confidenceSource: "human_review")).provenance == .human)
        // Present-but-unrecognised source is still a model, not a fabricated label.
        #expect(ClaimTableRow(claim(confidenceSource: "mlx-extractor")).provenance == .llm)
        // No source at all, not curated → honest unknown.
        #expect(ClaimTableRow(claim(confidenceSource: nil, curation: .unreviewed)).provenance == .unknown)
    }
}
