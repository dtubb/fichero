import FicheroAPIClient
import Foundation
import Observation

/// Observable store for the W3C SPARQL query layer (#3298). Wraps the typed
/// `POST /api/kg/query/sparql` (5s soft-timeout, #3297) and
/// `GET /api/kg/query/examples` ops — the query surface exists precisely so
/// this console can seed and run it. Never hand-rolls a URL.
@MainActor
@Observable
final class KGQueryStore {
    private(set) var response: Components.Schemas.SparqlResponse?
    private(set) var examples: [Components.Schemas.SparqlExampleQuery] = []
    private(set) var isRunning = false
    private(set) var errorMessage: String?

    private let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    func loadExamples() async {
        guard examples.isEmpty else { return }
        do {
            if case .ok(let response) = try await client.api.sparqlExamplesApiKgQueryExamplesGet() {
                examples = try response.body.json.examples
            }
        } catch {
            // Examples are an optional seed — a failure just leaves the menu empty.
        }
    }

    func run(query: String, limit: Int = 200) async {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        isRunning = true
        errorMessage = nil
        defer { isRunning = false }
        do {
            let output = try await client.api.sparqlQueryApiKgQuerySparqlPost(
                body: .json(.init(query: trimmed, limit: limit))
            )
            switch output {
            case .ok(let success):
                response = try success.body.json
            case .unprocessableContent(let error):
                response = nil
                errorMessage = (try? error.body.json)?.detail?.description ?? "Invalid query"
            case .undocumented(let code, _):
                response = nil
                errorMessage = "Query failed (HTTP \(code))"
            }
        } catch {
            response = nil
            errorMessage = error.localizedDescription
        }
    }

    /// Column names across all result rows (union of binding variables), sorted —
    /// the SPARQL projection isn't known until the query runs.
    static func columnKeys(_ rows: [Components.Schemas.SparqlResponseRow]) -> [String] {
        var keys = Set<String>()
        for row in rows {
            for key in row.bindings.additionalProperties.value.keys {
                keys.insert(key)
            }
        }
        return keys.sorted()
    }

    static func value(_ row: Components.Schemas.SparqlResponseRow, forKey key: String) -> String {
        guard let raw = row.bindings.additionalProperties.value[key], let raw else { return "" }
        return String(describing: raw)
    }
}
