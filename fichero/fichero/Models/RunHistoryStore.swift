import FicheroAPIClient
import Foundation
import Observation

/// What has been run on each document (#5434, `activity.document.what-has-been-run`): the engine's
/// `GET /api/documents/run-history?ids=…`, newest first, each entry as recorded when it ran (what,
/// the model and provider, when, the outcome, the cost when priced). The app never works an entry
/// out; it shows what the engine answered.
///
/// One per project (`LibraryReference.runHistoryStore`), over THAT project's client. A read asks for
/// many documents in one call and sets only the documents it asked for, each key on its own.
@MainActor
@Observable
final class RunHistoryStore {
    /// One thing run on a document, as the engine recorded it.
    struct Entry: Identifiable, Equatable {
        let id: String
        /// What it was, in words ("Find the lines", "Workflow run").
        let name: String
        /// The job kind (thumbnail, embed, find-lines, …) or "workflow".
        let kind: String
        /// done, failed, cancelled, waiting, running or paused.
        let state: String
        let reason: String?
        let model: String?
        let provider: String?
        /// Dollars; `nil` unless priced.
        let cost: Double?
        /// When it finished, else started, else was asked for.
        let when: Date?

        init(_ entry: Components.Schemas.RunHistoryEntry, index: Int) {
            self.init(
                id: entry.jobId ?? entry.threadId ?? "\(entry.documentId)#\(index)",
                name: entry.name, kind: entry.kind, state: entry.state, reason: entry.reason,
                model: entry.model, provider: entry.provider, cost: entry.cost, when: entry.at
            )
        }

        /// Test/preview seam — construct without the generated schema.
        init(
            id: String, name: String, kind: String = "", state: String, reason: String? = nil,
            model: String? = nil, provider: String? = nil, cost: Double? = nil, when: Date? = nil
        ) {
            self.id = id
            self.name = name
            self.kind = kind
            self.state = state
            self.reason = reason
            self.model = model
            self.provider = provider
            self.cost = cost
            self.when = when
        }

        /// The outcome in a word: "Done", "Failed", "Stopped", …
        var outcomeText: String {
            switch state.lowercased() {
            case "done", "completed": "Done"
            case "failed", "error": "Failed"
            case "cancelled", "canceled", "stopped": "Stopped"
            case "running": "Running"
            case "paused": "Paused"
            case "waiting": "Waiting"
            default: state.capitalized
            }
        }

        var isFailed: Bool { outcomeText == "Failed" }

        /// The model and the provider as recorded: "gpt-5 · openai", or either alone.
        var modelText: String? {
            let parts = [model, provider].compactMap { $0 }.filter { !$0.isEmpty }
            return parts.isEmpty ? nil : parts.joined(separator: " · ")
        }

        /// Dollars, as the price list states them, in any locale; `nil` unless priced.
        var costText: String? {
            cost.map { "$" + $0.formatted(.number.precision(.significantDigits(1...3)).locale(Locale(identifier: "en_US_POSIX"))) }
        }
    }

    /// Each document's history as last read, by document id. A document not read yet is absent.
    private(set) var histories: [String: [Entry]] = [:]
    /// Why the last read of a document failed, by document id.
    private(set) var failures: [String: String] = [:]

    private let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    /// The history of one document, newest first, or `nil` until it is read.
    func history(documentId: String) -> [Entry]? { histories[documentId] }

    /// Read the history of these documents in ONE call and set each asked-for document's own key
    /// (a document the engine withheld or had nothing for reads as empty). A failed read keeps what
    /// each document showed and says why.
    func load(documentIds: [String]) async {
        let ids = Array(Set(documentIds)).sorted()
        guard !ids.isEmpty else { return }
        let message: String
        do {
            switch try await client.api.getRunHistoryApiDocumentsRunHistoryGet(query: .init(ids: ids)) {
            case .ok(let success):
                let items = try success.body.json.items.additionalProperties
                for id in ids {
                    let entries = (items[id] ?? []).enumerated().map { Entry($0.element, index: $0.offset) }
                    if histories[id] != entries { histories[id] = entries }
                    if failures[id] != nil { failures[id] = nil }
                }
                return
            case .unprocessableContent:
                message = "The engine did not understand which documents to read."
            case .undocumented(let code, let payload):
                message = await EngineErrorDetail.message(from: payload)
                    ?? "Could not read what has been run (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return }
            message = "Could not read what has been run: \(error.localizedDescription)"
        }
        for id in ids where failures[id] != message { failures[id] = message }
    }
}
