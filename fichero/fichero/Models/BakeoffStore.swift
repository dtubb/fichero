import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime

/// Check on your pages: the bake-off for the reading step, the app half of
/// `/api/recipes/project/bakeoffs` (`source.try.bakeoff-is-the-same-tool`, section 8a; #4951).
/// The engine runs the one evaluation job on the project's corrected pages, ranks the readers by
/// the fixed order and keeps the comparison; this store only starts it, reads it back and sends
/// Use This. It never ranks, scores or decides a candidate itself.
///
/// One per project (`LibraryReference.bakeoffStore`), over that project's client, so a bake-off
/// started in setup is still there when the person leaves setup (it runs as a job in Activity)
/// and the project Inspector shows the same one. Each change replaces only the one comparison it
/// read; Use This changes only the reading step of the recipe it is given.
@MainActor
@Observable
final class BakeoffStore {
    typealias Comparison = Components.Schemas.BakeoffResult
    typealias Row = Components.Schemas.BakeoffRow

    /// The recipe step the bake-off compares (`recipes/bakeoff.STEP`): the reader.
    nonisolated static let step = "read-a-line"

    /// Where Use This applies (section 8a): the project, or just one folder.
    enum Scope: Hashable {
        case project
        case folder(id: String)
    }

    /// A folder Use This can be scoped to, as the picker names it.
    struct Folder: Hashable, Identifiable {
        let id: String
        let name: String
    }

    /// The project's newest comparison, as the engine last reported it.
    private(set) var comparison: Comparison?
    /// The engine's sentence when it would not run one (too few corrected lines, nothing it can
    /// score here). Shown once, plainly; while it stands there is no button to run.
    private(set) var refusal: String?
    private(set) var isStarting = false
    /// The card whose Use This is being sent.
    private(set) var usingCard: String?
    var errorMessage: String?

    private let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    /// Still waiting for, or inside, its evaluation job.
    var isRunning: Bool {
        guard let state = comparison?.state else { return false }
        return state == "waiting" || state == "running"
    }

    /// A run can be asked for: the engine has not refused, and none is under way.
    var canRun: Bool { refusal == nil && !isStarting && !isRunning }

    // MARK: Reading

    /// The newest comparison kept in the project (`GET /api/recipes/project/bakeoffs`, newest
    /// first), so setup and the Inspector reopen on it.
    func loadLatest() async {
        do {
            let items = try await client.api.listBakeoffsApiRecipesProjectBakeoffsGet().ok.body.json.items
            comparison = items.first
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read this project's comparisons: \(error.localizedDescription)"
        }
    }

    /// Read the comparison again (`GET …/bakeoffs/{id}`): its job's state and the table as the
    /// cards now score it. Called as its job in Activity moves on.
    func refresh() async {
        guard let id = comparison?.id else { return }
        do {
            switch try await client.api.bakeoffResultApiRecipesProjectBakeoffsBakeoffIdGet(path: .init(bakeoffId: id)) {
            case .ok(let success):
                comparison = try success.body.json
            case .unprocessableContent:
                errorMessage = "The engine did not understand which comparison to read."
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body)
                    ?? "Could not read the comparison (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read the comparison: \(error.localizedDescription)"
        }
    }

    // MARK: Running

    /// Compare the readers on the project's corrected pages (`POST …/bakeoffs`). The engine
    /// starts its evaluation job and answers with the comparison, or refuses in words (422), in
    /// which case nothing ran and its sentence stands in place of the button. Returns whether
    /// a comparison started.
    @discardableResult
    func start() async -> Bool {
        isStarting = true
        errorMessage = nil
        defer { isStarting = false }
        do {
            switch try await client.api.startBakeoffApiRecipesProjectBakeoffsPost() {
            case .ok(let success):
                comparison = try success.body.json
                refusal = nil
                return true
            case .unprocessableContent(let error):
                refusal = (try? error.body.json)?.detail?.description ?? "The engine would not compare readers here."
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body)
                    ?? "Could not compare readers (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return false }
            // The refusal is a sentence (`detail` a string), which the generated validation
            // shape cannot decode: say the engine's sentence, never the decoding error.
            if let words = await Self.engineWords(error) {
                refusal = words
            } else {
                errorMessage = "Could not compare readers: \(error.localizedDescription)"
            }
        }
        return false
    }

    // MARK: Use This

    /// Make a scored candidate the reading step's reader for the scope (`POST …/{id}/use`). The
    /// recipe on screen is saved first, so the engine sets the reader on the recipe the person
    /// sees; the recipe the engine then saved updates that one step in `setup`, in place.
    @discardableResult
    func use(_ row: Row, scope: Scope, in setup: RecipeSetupStore) async -> Bool {
        guard let id = comparison?.id, row.cer != nil else { return false }
        usingCard = row.card
        errorMessage = nil
        defer { usingCard = nil }
        if setup.recipe != nil, !(await setup.save()) {
            errorMessage = setup.errorMessage ?? "Could not save the recipe before using this reader."
            return false
        }
        let body: Components.Schemas.BakeoffUseRequest
        switch scope {
        case .project: body = .init(card: row.card, scope: .project)
        case .folder(let folder): body = .init(card: row.card, scope: .folder, folderId: folder)
        }
        do {
            switch try await client.api.useBakeoffChoiceApiRecipesProjectBakeoffsBakeoffIdUsePost(
                path: .init(bakeoffId: id), body: .json(body)
            ) {
            case .ok(let success):
                if let recipe = try success.body.json.recipe {
                    setup.adoptEngineRecipe(try JSONEncoder().encode(recipe))
                }
                return true
            case .unprocessableContent(let error):
                errorMessage = (try? error.body.json)?.detail?.description ?? "The engine would not use this reader."
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body) ?? "Could not use this reader (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return false }
            errorMessage = await Self.engineWords(error) ?? "Could not use this reader: \(error.localizedDescription)"
        }
        return false
    }

    /// Preview seams: a comparison or a refusal without an engine.
    func previewComparison(_ value: Comparison) { comparison = value }
    func previewRefusal(_ sentence: String) { refusal = sentence }

    private static func engineWords(_ error: Error) async -> String? {
        guard let clientError = error as? ClientError, let body = clientError.responseBody,
              let data = try? await Data(collecting: body, upTo: 1 << 16) else { return nil }
        return EngineErrorDetail.message(from: data)
    }
}

/// A bake-off row is one candidate, once: its card names it in the table.
extension Components.Schemas.BakeoffRow: @retroactive Identifiable {
    public var id: String { card }
}

// MARK: What a row says (the table draws exactly these, so they are checked without drawing)

extension BakeoffStore {
    /// A candidate by name, never its card id: the card's own name where the recipe's reading
    /// step carries it, else the kind of reader with its place by the rules (the bake-off's row
    /// does not carry the card's name yet).
    static func name(of row: Row, recipe: Components.Schemas.AssembledRecipe?) -> String {
        if let card = recipe?.steps.first(where: { $0.job == step })?.card,
           card.id == row.card, let note = card.note, !note.isEmpty {
            return note
        }
        let kind = switch row.reader {
        case .kraken: "Kraken reader"
        case .vision: row.local ? "Vision model" : "Cloud vision model"
        case .tesseract: "Tesseract"
        case nil: "Reader"
        }
        if let place = row.ruleRank {
            return "\(kind), the rules' \(place.formatted(.number))\(ordinalSuffix(place)) choice"
        }
        return "\(kind), the baseline for print"
    }

    private static func ordinalSuffix(_ place: Int) -> String {
        if (11...13).contains(place % 100) { return "th" }
        switch place % 10 {
        case 1: return "st"
        case 2: return "nd"
        case 3: return "rd"
        default: return "th"
        }
    }

    /// The character error rate as a percentage, or a dash with no score.
    static func errorRate(_ row: Row) -> String {
        guard let cer = row.cer else { return "—" }
        return cer.formatted(.percent.precision(.fractionLength(1)))
    }

    static func place(_ row: Row) -> String { row.local ? "This Mac" : "Cloud" }

    /// Why a candidate the engine names has no score, in the engine's words; empty when scored.
    static func note(_ row: Row) -> String {
        row.cer == nil ? row.why ?? "" : ""
    }

    /// Speed measured in this run.
    static func speed(_ row: Row) -> String {
        guard let perHour = row.pagesPerHour else { return "—" }
        return "\(Int(perHour.rounded()).formatted()) pages an hour"
    }

    /// The whole volume's cost, marked when it is an estimate.
    static func cost(_ row: Row) -> String {
        let figure = RecipeStartFields.cost(row.costUsd.value)
        return row.costUsd.basis == "estimate" && row.costUsd.value != nil ? "\(figure) (estimate)" : figure
    }
}
