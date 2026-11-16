import FicheroAPIClient
import Foundation
import Observation

/// One suggestion on the page it concerns (`wide.suggest.reason-and-override`, #6052): what the engine suggests, why, the answer or
/// measure that fired it, its price where it has one, and where Change… goes. The engine lists them
/// (`GET /api/recipes/suggestions`); the app reasons about none of it, it picks a page's rows and remembers which were changed.
struct SuggestionRow: Identifiable, Equatable {
    let id: String
    let what: String
    let why: String
    let from: String
    /// Already the project's answer.
    let applied: Bool
    /// The page or question Change… opens: "about-the-material.condition", "how.model-kind", "stage.<job>", "ready".
    let change: String
    let price: String?
    /// The person changed it: the row says "yours" and keeps the engine's reason beside it. A suggestion never acts by itself.
    var yours = false

    static let yoursWords = "Yours"

    init(id: String, what: String, why: String, from: String, applied: Bool = false, change: String,
         price: String? = nil, yours: Bool = false) {
        self.id = id; self.what = what; self.why = why; self.from = from; self.applied = applied
        self.change = change; self.price = price; self.yours = yours
    }

    init(engine row: Components.Schemas.Suggestion, yours: Bool = false) {
        id = row.id; what = row.what; why = row.why; from = row.from; applied = row.applied
        change = row.change; price = row.price; self.yours = yours
    }

    /// The line under the suggestion: its reason and where it came from, in the engine's words.
    var reasonLine: String { "\(why) (\(from))" }

    /// The page a row belongs to is the first part of its `change`.
    func isOn(page: String) -> Bool { change == page || change.hasPrefix(page + ".") }
}

/// Which page a list of rows is asked for.
enum SuggestionPage {
    case aboutTheMaterial, how, ready
    /// A stage page: the rows whose change names one of the stage's jobs.
    case stage(jobs: [String])

    func includes(_ row: SuggestionRow) -> Bool {
        switch self {
        case .aboutTheMaterial: return row.isOn(page: "about-the-material")
        case .how: return row.isOn(page: "how")
        case .ready: return row.isOn(page: "ready")
        case .stage(let jobs): return jobs.contains { row.isOn(page: "stage.\($0)") }
        }
    }
}

/// Loads the engine's list once per Set Up and remembers which suggestions the person changed (per run of the window, never stored).
@MainActor @Observable
final class SuggestionsStore {
    private let client: FicheroClient
    private(set) var rows: [SuggestionRow] = []
    private(set) var failure: String?
    private var changed: Set<String> = []

    init(client: FicheroClient, rows: [SuggestionRow] = []) {
        self.client = client
        self.rows = rows
    }

    func rows(on page: SuggestionPage) -> [SuggestionRow] { rows.filter(page.includes) }

    /// The person took Change… on this row: it reads "yours" from now on.
    func markChanged(_ id: String) {
        changed.insert(id)
        if let index = rows.firstIndex(where: { $0.id == id }) { rows[index].yours = true }
    }

    func load() async {
        do {
            switch try await client.api.suggestionsApiRecipesSuggestionsGet() {
            case .ok(let success):
                rows = try success.body.json.items.map { SuggestionRow(engine: $0, yours: changed.contains($0.id)) }
                failure = nil
            default:
                failure = "Could not read the suggestions."
            }
        } catch {
            if error.isCancellationError { return }
            failure = "Could not read the suggestions: \(error.localizedDescription)"
        }
    }
}
