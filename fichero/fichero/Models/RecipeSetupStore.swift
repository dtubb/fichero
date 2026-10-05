import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime

/// Setup's answers and the recipe the engine assembles from them
/// (`source/models-chains-and-projects.md` sections 7 and 8;
/// `source.onboard.purpose-first`, `source.onboard.deterministic-recipe`,
/// `source.onboard.self-documenting`). The app never decides a step or a model:
/// it sends the answers to `POST /api/recipes/assemble` and shows what the rules
/// gave back, and it explains each step with the topic registry's own words
/// (`TopicStore`, `GET /api/topics`), so setup, the Inspector and the manual say the
/// same thing. Proposes only; nothing runs and nothing is written.
@MainActor
@Observable
final class RecipeSetupStore {
    static let materials = ["handwriting", "print", "typescript"]

    // MARK: Answers (a draft until Start; nothing runs before it)

    /// How sources come into the project (ruled 2026-10-03,
    /// `source.sync.four-ways-in`): link (the default: originals read in place,
    /// never changed), copy (originals never touched), move (originals removed)
    /// or index (the folder worked on in place and kept up to date), the
    /// engine's folder ingest modes. Setup's Add a Folder… imports with it.
    var ingestMode: IngestMode = .link

    var purpose: String = "transcribe"
    var languages: [String] = []
    var scripts: [String] = []
    var material: String = "handwriting"
    /// Layers added beyond the purpose's (`source.onboard.add-layer`): the engine writes them
    /// (`POST /api/recipes/project/layers`); setup only carries them, into the recipe it asks
    /// for and the answers it saves, so no save drops what the engine added.
    private(set) var layers: [String] = []
    var pages: Int = 0
    /// May pages leave this Mac. Asked once per project; the default is that
    /// nothing leaves (`source.onboard.cloud-asked-once`).
    var cloudAllowed = false

    // MARK: What the engine gave back

    /// The purposes setup offers, from the engine (`GET /api/recipes/purposes`).
    private(set) var purposes: [Components.Schemas.PurposeInfo] = []
    private(set) var recipe: Components.Schemas.AssembledRecipe?
    private(set) var jobs: [String: Components.Schemas.JobInfo] = [:]
    /// The registry's own order, so what is offered after the recipe's steps is stable.
    private(set) var jobOrder: [String] = []
    /// What setup's Add a Folder… brought in, said back to the person.
    private(set) var materialAdded: String?
    private(set) var isAssembling = false
    private(set) var errorMessage: String?
    /// What the engine worked out for each chosen script: direction, whether it may be vertical,
    /// its bundled font (`source.onboard.derives-not-asks`). Keyed by ISO 15924 code.
    private(set) var derivedScripts: [String: Components.Schemas.ScriptFacts] = [:]

    /// Each step's explanation (`source.onboard.topics-written-once`): the library's
    /// own `TopicStore` where there is one.
    let topics: TopicStore

    private let client: FicheroClient

    init(client: FicheroClient, topics: TopicStore? = nil) {
        self.client = client
        self.topics = topics ?? TopicStore(client: client)
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
                savedAnswers = try JSONEncoder().encode(answers)
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
                answers: try JSONDecoder().decode(Components.Schemas.ProjectSetup.AnswersPayload.self,
                                                  from: answersToSave()),
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
                     pages: pages, cloudAllowed: cloudAllowed, ingestMode: ingestMode.rawValue.lowercased(),
                     layers: layers)
    }

    /// The answers as the project last saved them, as JSON, so a save keeps every field the
    /// engine wrote that setup does not ask about (`answers.layers`, `mac_memory_gb`, …).
    private var savedAnswers: Data?

    /// Setup's answers over the saved ones: a field setup asks about takes setup's value; any
    /// other field the engine saved stays as it was (`source.onboard.add-layer`).
    private func answersToSave() throws -> Data {
        var merged = (savedAnswers.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any]) ?? [:]
        let current = try JSONSerialization.jsonObject(with: JSONEncoder().encode(currentAnswers)) as? [String: Any] ?? [:]
        merged.merge(current) { _, new in new }
        return try JSONSerialization.data(withJSONObject: merged)
    }

    private func apply(_ saved: RecipeSetupAnswers) {
        if let value = saved.purpose { purpose = value }
        if let value = saved.languages { languages = value }
        layers = saved.layers ?? []
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

    /// One answer from setup's language or script search, as the field shows it.
    struct CodeChoice: Hashable {
        let code: String
        let name: String
        /// Where it came from, shown under the name: a dialect's language, a Glottolog code.
        let detail: String?
    }

    /// Search every language the engine knows: ISO 639-3 joined with Glottolog
    /// (`source.onboard.widget-and-search`). A languoid with no BCP 47 tag is added as a private-use
    /// tag carrying its glottocode, so nothing a person picks is lost.
    func searchLanguages(_ query: String) async -> [CodeChoice] {
        do {
            guard case .ok(let ok) = try await client.api.searchLanguagesApiRecipesLanguagesGet(
                query: .init(q: query, limit: 8)) else { return [] }
            return try ok.body.json.items.map { match in
                let code = match.code ?? match.glottocode.map { "und-x-\($0)" } ?? match.name
                let detail = [match.language.map { "dialect of \($0)" }, match.glottocode.map { "Glottolog \($0)" }]
                    .compactMap { $0 }.joined(separator: " · ")
                return CodeChoice(code: code, name: match.name, detail: detail.isEmpty ? nil : detail)
            }
        } catch {
            if !error.isCancellationError { errorMessage = "Could not search languages: \(error.localizedDescription)" }
            return []
        }
    }

    /// Search every ISO 15924 script.
    func searchScripts(_ query: String) async -> [CodeChoice] {
        do {
            guard case .ok(let ok) = try await client.api.searchScriptsApiRecipesScriptsGet(
                query: .init(q: query, limit: 8)) else { return [] }
            return try ok.body.json.items.map { CodeChoice(code: $0.code, name: $0.name, detail: nil) }
        } catch {
            if !error.isCancellationError { errorMessage = "Could not search scripts: \(error.localizedDescription)" }
            return []
        }
    }

    /// Ask the engine what it works out for the chosen scripts, rather than asking the person.
    func loadDerived() async {
        guard !scripts.isEmpty else { derivedScripts = [:]; return }
        do {
            guard case .ok(let ok) = try await client.api.derivedFactsApiRecipesDerivedGet(
                query: .init(scripts: scripts.joined(separator: ","))) else { return }
            for facts in try ok.body.json.scripts { derivedScripts[facts.script] = facts }
        } catch {
            if !error.isCancellationError { errorMessage = "Could not work out the scripts: \(error.localizedDescription)" }
        }
    }

    /// The job registry, once, with the topics that explain each job.
    func loadJobs() async {
        await topics.load()
        guard jobs.isEmpty else { return }
        do {
            if case .ok(let success) = try await client.api.listJobsApiRecipesJobsGet() {
                for job in try success.body.json.items where jobs[job.id] == nil {
                    jobs[job.id] = job
                    jobOrder.append(job.id)
                }
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
                    cloudAllowed: cloudAllowed,
                    // The layers added later stay in every recipe proposed again (source.onboard.add-layer).
                    layers: layers.isEmpty ? nil : layers
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

    /// The job's registered name, or nil when the registry does not know it
    /// (shown as such, never invented here).
    func job(for step: Components.Schemas.RecipeStep) -> Components.Schemas.JobInfo? {
        jobs[step.job]
    }

    /// What explains a job: its topic in the registry, or nil when the job names
    /// none the registry has (the job's name is shown alone).
    func explanation(ofJob id: String) -> Components.Schemas.TopicInfo? {
        topics.topic(jobs[id]?.topic)
    }

    /// A step's heading: its topic's title, else the job's registered name, else
    /// the bare job id. Never empty, never invented.
    func title(of step: Components.Schemas.RecipeStep) -> String {
        explanation(ofJob: step.job)?.title ?? jobs[step.job]?.name ?? step.job
    }

    // MARK: Offered first, never hidden (source.onboard.offers-never-hides)

    /// Every job in the registry, the purpose's recipe steps first (in the
    /// recipe's order), then the rest in the registry's order. A purpose
    /// changes what comes first; it never takes a job out of the list.
    var offeredJobs: [Components.Schemas.JobInfo] {
        let first = (recipe?.steps ?? []).map(\.job)
        var seen = Set<String>()
        return (first + jobOrder).compactMap { id in
            guard seen.insert(id).inserted else { return nil }
            return jobs[id]
        }
    }

    // MARK: Your material (source.sync.four-ways-in)

    /// Import a folder into the project the way setup chose (link, copy, move
    /// or index), through the project's own import path. Importing is not
    /// Start: no recipe step runs on it.
    func addFolder(_ url: URL, importer: ImportService) async {
        materialAdded = nil
        do {
            let ids = try await importer.importFolder(url, mode: ingestMode)
            materialAdded = "\(url.lastPathComponent): \(ids.count) added (\(ingestMode.displayName.lowercased()))."
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not add \(url.lastPathComponent): \(error.localizedDescription)"
        }
    }

    // MARK: Added later (source.onboard.add-layer)

    /// Change the project's languages after setup (from the Inspector):
    /// re-propose the recipe from the new answers and keep both on the
    /// project. Returns whether the engine kept them. Nothing runs.
    @discardableResult
    func updateLanguages(_ codes: [String]) async -> Bool {
        // Splice, so a language already there keeps its place (no wholesale reset).
        languages.removeAll { !codes.contains($0) }
        for code in codes where !languages.contains(code) { languages.append(code) }
        await assemble()
        guard recipe != nil else { return false }
        return await save()
    }

    /// Add a layer to the project, or with `remove` take an added one out
    /// (`POST /api/recipes/project/layers`, action `project.add_layer`, audited and undoable).
    /// The engine adds the layer's steps to the recipe and proposes its jobs for the material
    /// already there; the Start plan it returns shows them with the estimate. Nothing runs
    /// until Start. Afterwards the saved answers and recipe are read back, so a later save
    /// from setup or the Inspector carries the layer. Returns whether the engine kept it.
    @discardableResult
    func changeLayer(_ layer: String, remove: Bool = false) async -> Bool {
        errorMessage = nil
        do {
            switch try await client.api.changeProjectLayersApiRecipesProjectLayersPost(
                headers: .init(), body: .json(.init(layers: [layer], remove: remove))
            ) {
            case .ok(let success):
                startPlan = try success.body.json
                spliceLayer(layer, remove: remove)
                await adoptRecipeTheEngineWrote()
                return true
            case .unprocessableContent(let error):
                errorMessage = (try? error.body.json)?.detail?.description
                    ?? (remove ? "The engine would not remove the \(layer) layer" : "The engine would not add the \(layer) layer")
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body)
                    ?? "Could not change the project's layers (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return false }
            // A refusal in words ("the recipe already has entities") arrives as a 422 whose
            // `detail` is a sentence, which the generated validation shape cannot decode: say
            // the engine's sentence, never the decoding error.
            errorMessage = await Self.engineWords(error) ?? error.localizedDescription
        }
        return false
    }

    /// The engine kept the change: the one layer joins (or leaves) the answers in place, in
    /// `layers` and in the saved answers a later save starts from.
    private func spliceLayer(_ layer: String, remove: Bool) {
        if remove { layers.removeAll { $0 == layer } } else if !layers.contains(layer) { layers.append(layer) }
        var saved = (savedAnswers.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any]) ?? [:]
        saved["layers"] = layers
        savedAnswers = try? JSONSerialization.data(withJSONObject: saved)
    }

    /// The engine rewrote the recipe (the layer's steps joined it or left it, a model the person
    /// chose stayed): take that one object as the engine saved it, so a later save sends it
    /// back unchanged rather than the recipe from before the layer.
    private func adoptRecipeTheEngineWrote() async {
        do {
            guard case .ok(let success) = try await client.api.getProjectSetupApiRecipesProjectGet(),
                  let saved = try success.body.json.recipe else { return }
            recipe = try Self.convert(saved, to: Components.Schemas.AssembledRecipe.self)
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read the recipe the engine saved: \(error.localizedDescription)"
        }
    }

    /// The engine's own sentence from a response the generated client could not decode.
    private static func engineWords(_ error: Error) async -> String? {
        guard let clientError = error as? ClientError, let body = clientError.responseBody,
              let data = try? await Data(collecting: body, upTo: 1 << 16) else { return nil }
        return EngineErrorDetail.message(from: data)
    }

    /// The layers the Inspector offers to add, as the engine's Start plan names them
    /// (`addable`: the addable layers less those the project has and those its purpose
    /// brings). The app never works the rule out (`source.onboard.add-layer`).
    var addableLayers: [String] { startPlan?.addable ?? [] }

    /// What an added layer proposes for the material already in the project, with each step's
    /// topic text, as the engine's Start plan carries it; nil when nothing is proposed.
    var proposedJobs: Components.Schemas.ProposedJobs? {
        guard let proposed = startPlan?.proposed, !proposed.steps.isEmpty else { return nil }
        return proposed
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
    var layers: [String]?

    enum CodingKeys: String, CodingKey {
        case purpose, languages, scripts, material, pages, layers
        case cloudAllowed = "cloud_allowed"
        case ingestMode = "ingest_mode"
    }
}
