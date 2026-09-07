import FicheroAPIClient
import Foundation

/// One Wikidata statement offered for import (#3757 follow-on). Parsed from the
/// enrich/preview envelope; the sheet lists these with checkboxes. Marked
/// distinctly (a Wikidata badge) on import so "Wikidata says" never masquerades
/// as "the diary says".
struct WikidataStatementRow: Identifiable, Hashable {
    let statementId: String
    let propertyId: String
    let propertyLabel: String
    let valueLabel: String
    let valueQID: String?
    let valueURL: String?

    var id: String { statementId }

    /// The wire shape enrich/import expects for this statement.
    var importPayload: [String: Any] {
        var payload: [String: Any] = [
            "property_id": propertyId,
            "property_label": propertyLabel,
            "value_label": valueLabel,
        ]
        if let valueQID { payload["value_qid"] = valueQID }
        if let valueURL { payload["value_url"] = valueURL }
        return payload
    }
}

/// The reviewed enrichment preview: which QID, and its statements.
struct WikidataEnrichmentPreview: Equatable {
    let qid: String
    let subjectLabel: String
    let endpoint: String
    let statements: [WikidataStatementRow]
}

extension EntityStore {
    /// Fetch a linked entity's Wikidata statements for review (#3757 follow-on).
    /// The store is the only endpoint accessor (observable-data-layer); the sheet
    /// reads the returned preview. Throws so the sheet can surface the failure —
    /// notably a 403 when external authority enrichment is disabled, or a 502 when
    /// the SPARQL endpoint fails (never a silent empty result).
    func fetchWikidataStatements(
        entityId: String, qid: String? = nil
    ) async throws -> WikidataEnrichmentPreview {
        let data = try await entityService.enrichPreview(entityId: entityId, qid: qid)
        return Self.parseEnrichmentPreview(data)
    }

    /// Import the selected statements as WIKIDATA-SOURCED claims. Returns the
    /// number imported. Best-effort local refresh of the entity's claim count is
    /// left to the next reload / change-stream tick.
    @discardableResult
    func importWikidataStatements(
        entityId: String, qid: String, rows: [WikidataStatementRow]
    ) async throws -> Int {
        let data = try await entityService.enrichImport(
            entityId: entityId, qid: qid, statements: rows.map(\.importPayload)
        )
        return Self.parseImportedCount(data)
    }

    /// Parse the `{ qid, subject_label, endpoint, statements: [...] }` envelope.
    /// The `statements` schema is freeform (raw endpointData path), so parse
    /// defensively — a row missing property/value is dropped. Pure + exposed for
    /// tests.
    static func parseEnrichmentPreview(_ data: Data) -> WikidataEnrichmentPreview {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return WikidataEnrichmentPreview(qid: "", subjectLabel: "", endpoint: "", statements: [])
        }
        let rawStatements = obj["statements"] as? [[String: Any]] ?? []
        let statements = rawStatements.compactMap { item -> WikidataStatementRow? in
            guard let propertyId = item["property_id"] as? String,
                  let propertyLabel = item["property_label"] as? String,
                  let valueLabel = item["value_label"] as? String else { return nil }
            let statementId = item["statement_id"] as? String ?? "\(propertyId):\(valueLabel)"
            return WikidataStatementRow(
                statementId: statementId,
                propertyId: propertyId,
                propertyLabel: propertyLabel,
                valueLabel: valueLabel,
                valueQID: item["value_qid"] as? String,
                valueURL: item["value_url"] as? String
            )
        }
        return WikidataEnrichmentPreview(
            qid: obj["qid"] as? String ?? "",
            subjectLabel: obj["subject_label"] as? String ?? "",
            endpoint: obj["endpoint"] as? String ?? "",
            statements: statements
        )
    }

    static func parseImportedCount(_ data: Data) -> Int {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return 0
        }
        return obj["imported"] as? Int ?? 0
    }
}
