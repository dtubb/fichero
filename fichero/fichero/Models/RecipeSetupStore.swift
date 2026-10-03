import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime

/// Setup's answers and the recipe the engine assembles from them
/// (`source/models-chains-and-projects.md` sections 7 and 8;
/// `source.onboard.purpose-first`, `source.onboard.deterministic-recipe`,
/// `source.onboard.self-documenting`). The app never decides a step or a model:
/// it sends the answers to `POST /api/recipes/assemble` and shows what the rules
/// gave back, and it explains each step with the job registry's own words
/// (`GET /api/recipes/jobs`), so setup, the Inspector and the manual say the same
/// thing. Proposes only; nothing runs and nothing is written.
@MainActor
@Observable
final class RecipeSetupStore {
    static let materials = ["handwriting", "print", "typescript"]

    // MARK: Answers (a draft until Start; nothing runs before it)

    /// How sources come into the project (ruled 2026-10-03): link (the
    /// default: originals read in place, never changed), copy (originals never
    /// touched) or move (originals removed), the engine's ingest modes. Index,
    /// the two-way synced folder, has no mode yet (#4952), so it is not a value.
    var ingestMode: IngestMode = .link

    var purpose: String = "transcribe"
    var languages: [String] = []
    var scripts: [String] = []
    var material: String = "handwriting"
    var pages: Int = 0
    /// May pages leave this Mac. Asked once per project; the default is that
    /// nothing leaves (`source.onboard.cloud-asked-once`).
    var cloudAllowed = false

    // MARK: What the engine gave back

    /// The purposes setup offers, from the engine (`GET /api/recipes/purposes`).
    private(set) var purposes: [Components.Schemas.PurposeInfo] = []
    private(set) var recipe: Components.Schemas.AssembledRecipe?
    private(set) var jobs: [String: Components.Schemas.JobInfo] = [:]
    private(set) var isAssembling = false
    private(set) var errorMessage: String?

    private let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    /// The scripts and languages are the two facts the rules cannot do without
    /// (the engine requires at least one of each).
    var canAssemble: Bool { !languages.isEmpty && !scripts.isEmpty }

    /// Ask "may pages leave this Mac" only when a cloud model would fit a step
    /// (`source.onboard.cloud-asked-once`), or when the person already said yes
    /// (so the answer can be taken back).
    var asksCloudQuestion: Bool {
        cloudAllowed || !(recipe?.cloudOptions ?? []).isEmpty
    }

    /// The purposes, once, in the engine's order.
    func loadPurposes() async {
        guard purposes.isEmpty else { return }
        do {
            if case .ok(let success) = try await client.api.listPurposesApiRecipesPurposesGet() {
                purposes = try success.body.json.items
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read the purposes: \(error.localizedDescription)"
        }
    }

    // MARK: Saved on the project (GET/PUT /api/recipes/project)

    /// Fill the answers and the recipe from what the project already saved, so
    /// first run and Set Up… reopen where the person left off. Nothing saved
    /// leaves the defaults.
    func loadSaved() async {
        do {
            guard case .ok(let success) = try await client.api.getProjectSetupApiRecipesProjectGet() else { return }
            let saved = try success.body.json
            if let answers = saved.answers {
                apply(try Self.convert(answers, to: RecipeSetupAnswers.self))
            }
            if let savedRecipe = saved.recipe {
                recipe = try Self.convert(savedRecipe, to: Components.Schemas.AssembledRecipe.self)
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read this project's setup: \(error.localizedDescription)"
        }
    }

    /// Save the answers and the proposed recipe on the project. Saving is not
    /// Start: nothing runs. Returns whether the engine kept them.
    @discardableResult
    func save() async -> Bool {
        do {
            let body = Components.Schemas.ProjectSetup(
                answers: try Self.convert(currentAnswers, to: Components.Schemas.ProjectSetup.AnswersPayload.self),
                recipe: try recipe.map { try Self.convert($0, to: Components.Schemas.ProjectSetup.RecipePayload.self) }
            )
            switch try await client.api.saveProjectSetupApiRecipesProjectPut(headers: .init(), body: .json(body)) {
            case .ok:
                return true
            case .unprocessableContent(let error):
                errorMessage = (try? error.body.json)?.detail?.description ?? "The engine refused to save this setup"
            case .undocumented(let code, _):
                errorMessage = "Could not save this setup (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return false }
            errorMessage = error.localizedDescription
        }
        return false
    }

    // MARK: Start, the first yes (source.project.automatic-after-first-yes)

    /// What Start would run, on how many pages, with its estimate and any refusals,
    /// as the engine plans it (GET /api/recipes/project/start).
    private(set) var startPlan: Components.Schemas.StartPlan?

    /// Start is offered only when the engine has a plan with nothing refused.
    var canStart: Bool { startPlan.map { $0.refusals.isEmpty && !$0.workflows.isEmpty } ?? false }

    func loadStartPlan() async {
        do {
            if case .ok(let success) = try await client.api.getStartPlanApiRecipesProjectStartGet() {
                startPlan = try success.body.json
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read what Start would run: \(error.localizedDescription)"
        }
    }

    /// Record the first yes. Returns whether the engine kept it. The refused steps are
    /// already on screen (the plan loads with the step), so a refusal only says so.
    func start() async -> Bool {
        do {
            switch try await client.api.startProjectApiRecipesProjectStartPost() {
            case .ok(let success):
                startPlan = try success.body.json
                return true
            case .unprocessableContent:
                errorMessage = "Start was refused; the steps below say why."
            case .undocumented(let code, _):
                errorMessage = "Could not start (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return false }
            errorMessage = error.localizedDescription
        }
        return false
    }

    private var currentAnswers: RecipeSetupAnswers {
        RecipeSetupAnswers(purpose: purpose, languages: languages, scripts: scripts, material: material,
                     pages: pages, cloudAllowed: cloudAllowed, ingestMode: ingestMode.rawValue.lowercased())
    }

    private func apply(_ saved: RecipeSetupAnswers) {
        if let value = saved.purpose { purpose = value }
        if let value = saved.languages { languages = value }
        if let value = saved.scripts { scripts = value }
        if let value = saved.material { material = value }
        if let value = saved.pages { pages = value }
        if let value = saved.cloudAllowed { cloudAllowed = value }
        if let value = saved.ingestMode {
            // The engine's ingest modes are lowercase; the app's enum is upper.
            // An unknown mode is an error, never a silent fallback to link.
            guard let mode = IngestMode(rawValue: value.uppercased()) else {
                errorMessage = "This project's saved import choice “\(value)” is not one Fichero knows"
                return
            }
            ingestMode = mode
        }
    }

    /// One Codable shape to another through JSON: the generated object
    /// containers and the typed answers and recipe are the same JSON.
    private static func convert<From: Encodable, To: Decodable>(_ value: From, to type: To.Type) throws -> To {
        try JSONDecoder().decode(type, from: JSONEncoder().encode(value))
    }

    /// The job registry, once: each step's plain explanation comes from here.
    func loadJobs() async {
        guard jobs.isEmpty else { return }
        do {
            if case .ok(let success) = try await client.api.listJobsApiRecipesJobsGet() {
                for job in try success.body.json.items { jobs[job.id] = job }
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read the job registry: \(error.localizedDescription)"
        }
    }

    /// Ask the engine for the recipe these answers give. The same answers always
    /// give the same recipe, so this can run on every change.
    func assemble() async {
        guard canAssemble else { return }
        isAssembling = true
        errorMessage = nil
        defer { isAssembling = false }
        do {
            let output = try await client.api.assembleRecipeApiRecipesAssemblePost(
                body: .json(.init(
                    purpose: purpose,
                    languages: languages,
                    scripts: scripts,
                    material: material,
                    pages: pages,
                    cloudAllowed: cloudAllowed
                ))
            )
            switch output {
            case .ok(let success):
                recipe = try success.body.json
            case .unprocessableContent(let error):
                recipe = nil
                errorMessage = (try? error.body.json)?.detail?.description ?? "The engine refused these answers"
            case .undocumented(let code, _):
                recipe = nil
                errorMessage = "Could not assemble a recipe (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return }   // superseded by a newer answer
            recipe = nil
            errorMessage = error.localizedDescription
        }
    }

    /// The job's registered name and description, or nil when the registry does
    /// not know it (shown as such, never invented here).
    func job(for step: Components.Schemas.RecipeStep) -> Components.Schemas.JobInfo? {
        jobs[step.job]
    }
}

/// The answers as saved: the engine's own field names.
struct RecipeSetupAnswers: Codable, Equatable {
    var purpose: String?
    var languages: [String]?
    var scripts: [String]?
    var material: String?
    var pages: Int?
    var cloudAllowed: Bool?
    var ingestMode: String?

    enum CodingKeys: String, CodingKey {
        case purpose, languages, scripts, material, pages
        case cloudAllowed = "cloud_allowed"
        case ingestMode = "ingest_mode"
    }
}
