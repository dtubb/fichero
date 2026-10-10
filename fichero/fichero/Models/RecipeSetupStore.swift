import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime

/// Setup's answers and the recipe the engine assembles from them
/// (`source/models-chains-and-projects.md` sections 7b and 8;
/// `source.onboard.purpose-first`, `source.onboard.deterministic-recipe`,
/// `source.onboard.self-documenting`). The app never decides a step or a model:
/// it sends the answers to `POST /api/recipes/assemble` and shows what the rules
/// gave back, and it explains each step with the topic registry's own words
/// (`TopicStore`, `GET /api/topics`), so setup, the Inspector and the manual say the
/// same thing. Proposes only; nothing runs before Start.
///
/// One per project (`LibraryReference.recipeSetupStore`), over THAT project's client, so every
/// read and save names the project (#5477: the app-wide client sent no project path and the
/// engine answered 400).
@MainActor
@Observable
final class RecipeSetupStore {
    static let materialKinds = ["handwriting", "print", "typescript"]
    /// The directions setup offers, as the engine names them (`recipes/answers.SETUP_DIRECTIONS`).
    static let directionChoices: [(id: String, title: String)] = [
        ("ltr", "Left to right"), ("rtl", "Right to left"),
        ("ttb", "Top to bottom, columns right to left"), ("ttb-lr", "Top to bottom, columns left to right")
    ]

    // MARK: Answers (a draft until Start; nothing runs before it)

    /// How sources come into the project (ruled 2026-10-03,
    /// `source.sync.four-ways-in`): link (the default: originals read in place,
    /// never changed), copy (originals never touched), move (originals removed)
    /// or index (the folder worked on in place and kept up to date), the
    /// engine's folder ingest modes. Setup's Add a Folder… imports with it.
    var ingestMode: IngestMode = .link
    /// Keep arranged (#5480, `source.onboard.keep-arranged`): Index, and Fichero also keeps the
    /// folder's files arranged by the project's folders. Only with `ingestMode == .index`.
    var keepsArranged = false

    /// The five ways in as setup offers them (`source.onboard.five-ways-in`): the import's mode,
    /// and for Keep arranged, Index plus arrangement.
    var wayIn: SetupWayIn {
        get { keepsArranged && ingestMode == .index ? .keepArranged : SetupWayIn(ingestMode) }
        set {
            ingestMode = newValue.ingestMode
            keepsArranged = newValue == .keepArranged
        }
    }

    /// The purposes ticked (section 7b screen 2, #5478): any combination; none is "Not sure yet".
    var purposes: [String] = ["transcribe"]
    /// Jobs ticked on their own, beyond the purposes' (`answers.jobs`).
    var addedJobs: [String] = []
    /// Steps (by job) the person took out of the plan on Ready (#5627, `answers.removed_jobs`): the engine leaves
    /// them out of every recipe it proposes, unless a step left in needs one.
    var removedJobs: [String] = []
    /// Language tags (`es`, `und-x-<glottocode>`), never the typed word (#5479).
    var languages: [String] = []
    /// ISO 15924 codes.
    var scripts: [String] = []
    /// One direction per script (`ltr`, `rtl`, `ttb`, `ttb-lr`), pre-filled from the script.
    var directions: [String: String] = [:]
    /// Handwriting, print, typescript: any mix, at least one (#5478).
    var materials: [String] = ["handwriting"]
    /// Scripts setup put in because a chosen language is usually written in them (#5626), each with the languages
    /// that proposed it: a language taken out again takes out a script only it proposed.
    private(set) var proposedScripts: [String: Set<String>] = [:]
    /// What each chosen tag or code is called, for its token; a saved code with no name here
    /// shows as the code.
    private(set) var names: [String: String] = [:]
    /// Layers added beyond the purpose's (`source.onboard.add-layer`): the engine writes them
    /// (`POST /api/recipes/project/layers`); setup only carries them, into the recipe it asks
    /// for and the answers it saves, so no save drops what the engine added.
    private(set) var layers: [String] = []
    var pages: Int = 0
    /// May pages leave this Mac. Asked once per project; the default is that
    /// nothing leaves (`source.onboard.cloud-asked-once`).
    var cloudAllowed = false
    /// What runs by itself after Start (`source.onboard.what-runs-by-itself`): nil until the
    /// person or the saved answers say, then whether new material runs, and through which steps.
    var automatic: RecipeSetupAnswers.Automatic?
    /// The questions a ticked purpose opens under it (section 7b step 3, `answers.job_answers`).
    var jobAnswers = RecipeSetupAnswers.JobAnswers()

    // MARK: What the engine gave back

    /// The purposes setup offers, each with its jobs, from the engine (`GET /api/recipes/purposes`).
    private(set) var purposeOptions: [Components.Schemas.PurposeInfo] = []
    private(set) var recipe: Components.Schemas.AssembledRecipe?
    private(set) var jobs: [String: Components.Schemas.JobInfo] = [:]
    /// The registry's own order, so what is offered after the recipe's steps is stable.
    private(set) var jobOrder: [String] = []
    /// What setup's Add a Folder… brought in, said back to the person.
    private(set) var materialAdded: String?
    /// The folder Add a Folder… tied as a synced folder (Index), shown on the screen with its intake.
    private(set) var tiedFolderPath: String?
    private(set) var isAssembling = false
    var errorMessage: String?
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

    /// The project this store reads and saves (the client's library path); nil is the app-wide
    /// client, which the engine refuses for a project's setup (#5477).
    var projectPath: String? { client.currentLibraryPath }

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
        guard purposeOptions.isEmpty else { return }
        do {
            if case .ok(let success) = try await client.api.listPurposesApiRecipesPurposesGet() {
                purposeOptions = try success.body.json.items
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read the purposes: \(error.localizedDescription)"
        }
    }

    // MARK: Purposes and jobs as checkboxes (#5478)

    /// Tick or untick a purpose. None ticked is "Not sure yet" (the engine reads an empty list so).
    func toggle(purpose id: String) {
        if let index = purposes.firstIndex(of: id) {
            purposes.remove(at: index)
        } else {
            purposes.append(id)
            // Ticking a purpose asks for its jobs: a step taken out on Ready that it brings comes back (#5627).
            let brings = Set(purposeOptions.first { $0.id == id }?.jobs?.map(\.id) ?? [])
            removedJobs.removeAll { brings.contains($0) }
        }
    }

    /// The ticked purpose that already includes this one, when it is listed under it (#5625): its parent, ticked,
    /// whose jobs hold every one of this purpose's (the knowledge graph holds Entities and Statements). Shown
    /// ticked and fixed while the parent is; nil otherwise.
    func includingPurpose(of id: String) -> Components.Schemas.PurposeInfo? {
        guard !purposes.contains(id), let option = purposeOptions.first(where: { $0.id == id }),
              let parentId = option.parent, purposes.contains(parentId),
              let parent = purposeOptions.first(where: { $0.id == parentId }) else { return nil }
        let held = Set((parent.jobs ?? []).map(\.id))
        return (option.jobs ?? []).allSatisfy { held.contains($0.id) } ? parent : nil
    }

    // MARK: What runs by itself (source.onboard.what-runs-by-itself)

    /// The one choice on Ready: Nothing runs automatically, or new material runs through the
    /// recipe's steps (the purposes' proposal where there is one, else every step but training,
    /// `source.recipe.train-never-automatic`).
    func setRunsByItself(_ runs: Bool) {
        var steps = automaticAnswer.steps
        if runs && steps.isEmpty {
            steps = (recipe?.steps ?? []).map(\.job).filter { $0 != "train-a-model" }
        }
        automatic = .init(runs: runs, steps: steps)
    }

    /// The proposal before the person says: steps of a purpose that runs by itself are ticked
    /// (training never is, `source.recipe.train-never-automatic`); with none, nothing runs.
    var proposedAutomatic: RecipeSetupAnswers.Automatic {
        let running = purposeOptions.filter { purposes.contains($0.id) && $0.runsByItself }
        let jobs = Set(running.flatMap { ($0.jobs ?? []).map(\.id) })
        let steps = (recipe?.steps ?? []).map(\.job).filter { jobs.contains($0) && $0 != "train-a-model" }
        return .init(runs: !steps.isEmpty, steps: steps)
    }

    /// What runs by itself: the person's answer, else the proposal.
    var automaticAnswer: RecipeSetupAnswers.Automatic { automatic ?? proposedAutomatic }

    // MARK: Saved on the project (GET/PUT /api/recipes/project)

    /// Fill the answers and the recipe from what the project already saved, so
    /// setup reopens where the person left off. Nothing saved leaves the defaults.
    func loadSaved() async {
        do {
            guard case .ok(let success) = try await client.api.getProjectSetupApiRecipesProjectGet() else { return }
            let saved = try success.body.json
            if let answers = saved.answers {
                savedAnswers = try JSONEncoder().encode(answers)
                apply(try Self.convert(answers, to: RecipeSetupAnswers.self))
            }
            if let savedRecipe = saved.recipe {
                rememberOverrides(from: try JSONEncoder().encode(savedRecipe))
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
                recipe: try recipe.map { try recipePayload($0) }
            )
            switch try await client.api.saveProjectSetupApiRecipesProjectPut(headers: .init(), body: .json(body)) {
            case .ok:
                return true
            case .unprocessableContent(let error):
                errorMessage = (try? error.body.json)?.detail?.description ?? "The engine refused to save this setup"
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body) ?? "Could not save this setup (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return false }
            errorMessage = await Self.engineWords(error) ?? error.localizedDescription
        }
        return false
    }

    // MARK: Start, the first yes (source.project.automatic-after-first-yes)

    /// What Start would run, on how many pages, with its estimate and any refusals,
    /// as the engine plans it (GET /api/recipes/project/start).
    private(set) var startPlan: Components.Schemas.StartPlan?

    /// Start is offered only when the engine has a plan with nothing refused.
    var canStart: Bool { startPlan.map { $0.refusals.isEmpty && !$0.workflows.isEmpty } ?? false }

    /// The folder the shown plan covers (`source.recipe.folder-scoped-start`); nil: the whole project.
    private(set) var startPlanFolderId: String?

    /// Read what Start would run: on the whole project, or with `folderId` on that folder alone (its
    /// live pages, its folders inside it included; `source.recipe.folder-scoped-start`).
    func loadStartPlan(folderId: String? = nil) async {
        do {
            if case .ok(let success) = try await client.api.getStartPlanApiRecipesProjectStartGet(
                query: .init(folderId: folderId)
            ) {
                startPlan = try success.body.json
                if startPlanFolderId != folderId { startPlanFolderId = folderId }
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read what Start would run: \(error.localizedDescription)"
        }
    }

    /// A download that finished (#5583, `source.onboard.auto.installed-model-first`): the engine says
    /// `model.installed` on the project's change stream, and the plan on screen is read again, so the
    /// step that waited for that model stops waiting without a press. Only a plan already shown is
    /// read again; a store that never showed one has nothing waiting.
    func modelInstalled() {
        guard startPlan != nil else { return }
        Task { await loadStartPlan(folderId: startPlanFolderId) }
    }

    /// Record the first yes. Returns whether the engine kept it. The refused steps are
    /// already on screen (the plan loads with the step), so a refusal only says so.
    /// With `folderId`, the run covers that folder's live pages alone (`source.recipe.folder-scoped-start`);
    /// without it, the whole project, sent as before (no body).
    func start(folderId: String? = nil) async -> Bool {
        do {
            let response: Operations.StartProjectApiRecipesProjectStartPost.Output
            if let folderId {
                response = try await client.api.startProjectApiRecipesProjectStartPost(
                    body: .json(.init(folderId: folderId))
                )
            } else {
                response = try await client.api.startProjectApiRecipesProjectStartPost()
            }
            switch response {
            case .ok(let success):
                startPlan = try success.body.json
                if startPlanFolderId != folderId { startPlanFolderId = folderId }
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

    /// The recipe run Start queued (`run-a-recipe`), once the engine has kept the first yes: setup
    /// closes onto it (#5576, `source.onboard.auto.lands-on-the-run`).
    var startedRunJobId: String? { startPlan?.started?.jobId }

    // MARK: What will not run (#5573, `source.onboard.auto.plan-shows-what-will-not-run`)

    /// The steps Start skips, each with the engine's why and its fix (`fix`), as the plan has them.
    var skippedSteps: [Components.Schemas.SkippedStep] { startPlan?.skipped ?? [] }

    /// The models the plan's steps need that are not on this Mac, each with its size and the download.
    var downloads: [Components.Schemas.StartDownload] { startPlan?.downloads ?? [] }

    /// The models the plan's steps are pinned to that this Mac cannot run, each with the free places offered
    /// instead (#5592, `ai.where.fallback-free-and-asked`).
    var elsewhere: [Components.Schemas.StartElsewhere] { startPlan?.elsewhere ?? [] }

    /// The downloads asked for here, by model, while the engine fetches them (a `download-model` job).
    private(set) var downloading: Set<String> = []

    /// A skipped step by its title in the recipe ("Find names"), else by its id.
    func title(ofStepId step: String) -> String {
        guard let found = recipe?.steps.first(where: { $0.id == step }) else { return step }
        return title(of: found)
    }

    /// Fetch a model the plan needs, through the one download route
    /// (`POST /api/local-models/download/{runtime}/{model}`); the row says Downloading…. The step
    /// stays refused until the download has finished; the engine then says `model.installed` and the plan is read again (`modelInstalled()`).
    func download(_ download: Components.Schemas.StartDownload) async {
        do {
            let response = try await client.api.downloadModelApiLocalModelsDownloadModelTypeModelIdPost(
                path: .init(modelType: download.runtime, modelId: download.model)
            )
            switch response {
            case .ok:
                downloading.insert(download.model)
            case .unprocessableContent:
                errorMessage = "Could not download \(download.model)."
            case .undocumented(let code, _):
                errorMessage = "Could not download \(download.model) (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not download \(download.model): \(error.localizedDescription)"
        }
    }

    /// Use the installed model the plan offers instead of a download (#5583,
    /// `source.onboard.auto.installed-model-first`): the engine sets it on the steps that waited for
    /// the download and saves the recipe; the changed steps replace theirs in place, and Ready reads
    /// the plan again because the recipe changed.
    func useInstead(_ download: Components.Schemas.StartDownload,
                    _ installed: Components.Schemas.StartInstead) async {
        do {
            switch try await client.api.useInstalledInsteadApiRecipesProjectStartUseInsteadPost(
                body: .json(.init(model: download.model, card: installed.card))
            ) {
            case .ok(let success):
                if let recipe = try success.body.json.recipe {
                    adoptEngineRecipe(try JSONEncoder().encode(recipe))
                }
            case .unprocessableContent(let error):
                errorMessage = (try? error.body.json)?.detail?.description
                    ?? "The engine would not use \(installed.name)."
            case .undocumented(let code, _):
                errorMessage = "Could not use \(installed.name) (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not use \(installed.name): \(error.localizedDescription)"
        }
    }

    /// Use for This Step on any candidate the finder lists (#5612, `source.find.app-card-actions`): the
    /// engine sets it as the step's reader, kept as the project's override, and saves the recipe
    /// (audited, undoable); the changed step replaces its own in place, as with `useInstead`.
    func useCandidate(_ candidate: Components.Schemas.ModelCandidate, forStep step: String) async {
        do {
            switch try await client.api.useCandidateForStepApiRecipesProjectStepsUseCandidatePost(
                body: .json(.init(step: step, card: candidate.id))
            ) {
            case .ok(let success):
                if let recipe = try success.body.json.recipe {
                    adoptEngineRecipe(try JSONEncoder().encode(recipe))
                }
            case .unprocessableContent(let error):
                errorMessage = (try? error.body.json)?.detail?.description
                    ?? "The engine would not use \(candidate.name) for this step."
            case .undocumented(let code, _):
                errorMessage = "Could not use \(candidate.name) (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not use \(candidate.name): \(error.localizedDescription)"
        }
    }

    /// Run the model this Mac cannot run at the free place the plan offers (#5592,
    /// `ai.where.fallback-free-and-asked`): only on this press, the engine sets the same model at that
    /// place on the steps and saves the recipe; the changed steps replace theirs in place, and Ready
    /// reads the plan again because the recipe changed.
    func useFreePlace(_ entry: Components.Schemas.StartElsewhere,
                      _ place: Components.Schemas.StartPlaceInstead) async {
        do {
            switch try await client.api.useInstalledInsteadApiRecipesProjectStartUseInsteadPost(
                body: .json(.init(model: entry.model, provider: place.provider))
            ) {
            case .ok(let success):
                if let recipe = try success.body.json.recipe {
                    adoptEngineRecipe(try JSONEncoder().encode(recipe))
                }
            case .unprocessableContent(let error):
                errorMessage = (try? error.body.json)?.detail?.description
                    ?? "The engine would not run \(entry.name) at \(place.providerName)."
            case .undocumented(let code, _):
                errorMessage = "Could not run \(entry.name) at \(place.providerName) (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not run \(entry.name) at \(place.providerName): \(error.localizedDescription)"
        }
    }

    // MARK: What the engine wrote on the recipe (Use This, #4951)

    /// The recipe's `overrides` as the engine last saved them (Use This writes them,
    /// `source.try.use-this-scope`). A recipe proposed for an open project carries them (and a
    /// project-scope one has already set its step's reader); one that does not (read before the
    /// engine sent them) has them kept here and sent back with every save, so a save never drops
    /// a reader the person chose.
    @ObservationIgnored private var savedRecipeOverrides: Data?

    private func rememberOverrides(from recipeJSON: Data) {
        guard let object = try? JSONSerialization.jsonObject(with: recipeJSON) as? [String: Any],
              let overrides = object["overrides"] else { return }
        savedRecipeOverrides = try? JSONSerialization.data(withJSONObject: overrides)
    }

    /// The recipe as saved: the one on screen, with the engine's overrides kept.
    private func recipePayload(_ recipe: Components.Schemas.AssembledRecipe) throws
        -> Components.Schemas.ProjectSetup.RecipePayload {
        var object = (try JSONSerialization.jsonObject(with: JSONEncoder().encode(recipe)) as? [String: Any]) ?? [:]
        if object["overrides"] == nil, let kept = savedRecipeOverrides,
           let overrides = try? JSONSerialization.jsonObject(with: kept) {
            object["overrides"] = overrides
        }
        return try JSONDecoder().decode(Components.Schemas.ProjectSetup.RecipePayload.self,
                                        from: JSONSerialization.data(withJSONObject: object))
    }

    /// The recipe the engine saved after a change it made itself (Use This): each step it
    /// changed replaces the step with its id, in place, so only that row redraws; its overrides
    /// are kept for the next save.
    func adoptEngineRecipe(_ recipeJSON: Data) {
        rememberOverrides(from: recipeJSON)
        guard let saved = try? JSONDecoder().decode(Components.Schemas.AssembledRecipe.self, from: recipeJSON) else {
            errorMessage = "Could not read the recipe the engine saved."
            return
        }
        guard let current = recipe else {
            recipe = saved
            return
        }
        for step in saved.steps {
            if let index = current.steps.firstIndex(where: { $0.id == step.id }), current.steps[index] != step {
                recipe?.steps[index] = step
            }
        }
        // A recipe proposed for the project carries its overrides; the engine's newer ones replace
        // them, so the next save does not send back the list from before this change.
        if current.overrides != saved.overrides {
            recipe?.overrides = saved.overrides
        }
    }

    private var currentAnswers: RecipeSetupAnswers {
        RecipeSetupAnswers(purposes: purposes, jobs: addedJobs, languages: languages, scripts: scripts,
                           directions: directions, materials: materials, pages: pages,
                           cloudAllowed: cloudAllowed, ingestMode: wayIn.savedName,
                           layers: layers, automatic: automatic, jobAnswers: jobAnswers, removedJobs: removedJobs)
    }

    /// The answers as the project last saved them, as JSON, so a save keeps every field the
    /// engine wrote that setup does not ask about (`answers.layers`, `mac_memory_gb`, …).
    private var savedAnswers: Data?

    /// Setup's answers over the saved ones: a field setup asks about takes setup's value; any
    /// other field the engine saved stays as it was (`source.onboard.add-layer`). The old
    /// single `purpose` and `material` give way to the lists.
    private func answersToSave() throws -> Data {
        var merged = (savedAnswers.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any]) ?? [:]
        merged.removeValue(forKey: "purpose")
        merged.removeValue(forKey: "material")
        let current = try JSONSerialization.jsonObject(with: JSONEncoder().encode(currentAnswers)) as? [String: Any] ?? [:]
        merged.merge(current) { _, new in new }
        return try JSONSerialization.data(withJSONObject: merged)
    }

    private func apply(_ saved: RecipeSetupAnswers) {
        // A project saved before 2026-10-05 holds one purpose and one material: a list of one.
        if let value = saved.purposes ?? saved.purpose.map({ [$0] }) {
            purposes = value.filter { $0 != "not-sure" }
        }
        if let value = saved.jobs { addedJobs = value }
        if let value = saved.removedJobs { removedJobs = value }
        if let value = saved.languages { languages = value }
        layers = saved.layers ?? []
        if let value = saved.scripts { scripts = value }
        if let value = saved.directions { directions = value }
        if let value = saved.materials ?? saved.material.map({ [$0] }), !value.isEmpty { materials = value }
        if let value = saved.pages { pages = value }
        if let value = saved.cloudAllowed { cloudAllowed = value }
        if let value = saved.automatic { automatic = value }
        if let value = saved.jobAnswers { jobAnswers = value }
        if let value = saved.ingestMode {
            // The engine's ingest modes are lowercase; the app's enum is upper.
            // An unknown mode is an error, never a silent fallback to link.
            guard let way = SetupWayIn(savedName: value) else {
                errorMessage = "This project's saved import choice “\(value)” is not one Fichero knows"
                return
            }
            wayIn = way
        }
    }

    /// One Codable shape to another through JSON: the generated object
    /// containers and the typed answers and recipe are the same JSON.
    private static func convert<From: Encodable, To: Decodable>(_ value: From, to type: To.Type) throws -> To {
        try JSONDecoder().decode(type, from: JSONEncoder().encode(value))
    }

}

// The plan's steps as checkboxes, and what each step asks (moved out of the class body for its length).
extension RecipeSetupStore {
    // MARK: Editing the plan on Ready (#5627, source.onboard.plan-editable)

    /// Whether a step can be taken out: the engine names, in `needed_by`, the later steps that need it.
    static func canTakeOut(_ step: Components.Schemas.RecipeStep) -> Bool { (step.neededBy ?? []).isEmpty }

    /// Take a step out of the plan; the engine proposes the plan again without it, and Ready saves that, so
    /// Start runs the plan as shown and Set Up… reopens with it.
    func takeOut(job: String) async {
        guard !removedJobs.contains(job) else { return }
        removedJobs.append(job)
        await assemble()
    }

    /// Put a step taken out back into the plan.
    func putBack(job: String) async {
        removedJobs.removeAll { $0 == job }
        await assemble()
    }

    /// Tick or untick a job on its own. A job a ticked purpose brings stays ticked while that
    /// purpose is (the engine adds jobs to a purpose's, it never takes one away).
    func toggle(job id: String) {
        if let index = addedJobs.firstIndex(of: id) { addedJobs.remove(at: index) } else { addedJobs.append(id) }
    }

    /// The jobs the ticked purposes bring, as the engine lists them (`PurposeInfo.jobs`).
    var jobsFromPurposes: Set<String> {
        Set(purposeOptions.filter { purposes.contains($0.id) }.flatMap { ($0.jobs ?? []).map(\.id) })
    }

    /// Every ticked job, each once: the purposes' and those ticked on their own, in the
    /// registry's order (the recipe's step order) where the registry is loaded.
    var tickedJobs: [String] {
        let ticked = jobsFromPurposes.union(addedJobs)
        let ordered = jobOrder.filter { ticked.contains($0) }
        return ordered + ticked.subtracting(ordered).sorted()
    }

    /// The jobs that ask the person something the engine cannot work out (section 7b, step 3):
    /// which kinds of names, which gazetteer, into what form. Every other job's settings have
    /// defaults and live in the Inspector.
    static let jobsWithQuestions: Set<String> = [
        "find-names-tag-words", "place-in-a-gazetteer", "translate-transliterate-normalise"
    ]

    /// The jobs whose questions open in place under a ticked purpose (ruled 2026-10-06, #5492):
    /// that purpose's jobs that ask something, in its own order, each asked once, under the first
    /// ticked purpose (in the engine's order) that brings it. An unticked purpose asks nothing.
    func questions(under purpose: String) -> [String] {
        guard purposes.contains(purpose) else { return [] }
        var asked = Set<String>()
        for option in purposeOptions where purposes.contains(option.id) {
            let asking = (option.jobs ?? []).map(\.id).filter { Self.jobsWithQuestions.contains($0) && !asked.contains($0) }
            if option.id == purpose { return asking }
            asked.formUnion(asking)
        }
        return []
    }
}

// Behaviour over the stored answers above, in an extension so the class body holds the state.
extension RecipeSetupStore {
    // MARK: Languages and scripts (#5479)

    /// One answer from setup's language or script search, as the field shows it.
    struct CodeChoice: Hashable {
        let code: String
        let name: String
        /// Where it came from, shown under the name: a dialect's language, a Glottolog code.
        let detail: String?
        /// For a language, the script it is usually written in (ISO 15924) and that script's name (#5626).
        var usualScript: String?
        var usualScriptName: String?
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
                return CodeChoice(code: code, name: match.name, detail: detail.isEmpty ? nil : detail,
                                  usualScript: match.script, usualScriptName: match.scriptName)
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

    /// What a match in the dropdown puts in the field when picked: its name and its tag, so two
    /// matches with one name (a language and its dialect) stay apart, and the pick is found again
    /// by `pick(_:among:toScripts:)`. Type-to-find only (ruled 2026-10-05): no browse list.
    static func completion(for choice: CodeChoice) -> String { "\(choice.name) (\(choice.code))" }

    /// The field's text after a change: when it is a match's completion (the person picked it in
    /// the dropdown), that match becomes a token, by its tag, and true is returned so the field
    /// clears. Anything else is still being typed.
    @discardableResult
    func pick(_ text: String, among matches: [CodeChoice], toScripts: Bool) -> Bool {
        guard let choice = matches.first(where: { Self.completion(for: $0) == text }) else { return false }
        add(choice, toScripts: toScripts)
        return true
    }

    /// Add a chosen language or script as a token, by its tag or code, keeping its name.
    func add(_ choice: CodeChoice, toScripts: Bool) {
        names[choice.code] = choice.name
        if toScripts {
            guard !scripts.contains(choice.code) else { return }
            scripts.append(choice.code)
        } else if !languages.contains(choice.code) {
            languages.append(choice.code)
            proposeScript(for: choice)
        }
    }

    /// A language chosen proposes the script it is usually written in (#5626, `source.onboard.script-from-language`):
    /// English adds Latin, Russian Cyrillic, unless the script is already there. The person removes it or adds
    /// another like any token; a language with no usual script on record proposes nothing.
    private func proposeScript(for language: CodeChoice) {
        guard let script = language.usualScript else { return }
        if !scripts.contains(script) {
            names[script] = language.usualScriptName ?? script
            scripts.append(script)
            proposedScripts[script] = []
        }
        proposedScripts[script]?.insert(language.code)
    }

    /// What the person typed and pressed Return on: the engine's best answer becomes the token
    /// (a name the registry has exactly, else its first match: "spanish" is Spanish, `es`), and
    /// a word it does not know is refused in words, never kept as typed (#5479).
    @discardableResult
    func addTyped(_ typed: String, toScripts: Bool) async -> Bool {
        let word = typed.trimmingCharacters(in: .whitespaces)
        guard !word.isEmpty else { return false }
        let matches = toScripts ? await searchScripts(word) : await searchLanguages(word)
        let lowered = word.lowercased()
        guard let choice = matches.first(where: { $0.name.lowercased() == lowered || $0.code.lowercased() == lowered })
                ?? matches.first else {
            errorMessage = "Fichero doesn't know a \(toScripts ? "script" : "language") called “\(word)”."
            return false
        }
        add(choice, toScripts: toScripts)
        return true
    }

    /// The name of a tag or code where setup knows it; else the code itself.
    func name(of code: String) -> String { names[code] ?? code }

    /// Remove a token.
    func remove(_ code: String, fromScripts: Bool) {
        if fromScripts {
            scripts.removeAll { $0 == code }
            directions.removeValue(forKey: code)
            proposedScripts.removeValue(forKey: code)
        } else {
            languages.removeAll { $0 == code }
            // A script only this language proposed goes with it; one the person chose, or another language
            // proposed, stays.
            for (script, proposers) in proposedScripts where proposers.contains(code) {
                proposedScripts[script]?.remove(code)
                if proposedScripts[script]?.isEmpty == true {
                    proposedScripts.removeValue(forKey: script)
                    scripts.removeAll { $0 == script }
                    directions.removeValue(forKey: script)
                }
            }
        }
    }

    /// The direction a script is read in: the person's choice, else the engine's derived fact.
    func direction(of script: String) -> String {
        directions[script] ?? derivedScripts[script]?.direction ?? "ltr"
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
                    purposes: purposes,
                    languages: languages,
                    scripts: scripts,
                    materials: materials,
                    jobs: addedJobs.isEmpty ? nil : addedJobs,
                    removedJobs: removedJobs.isEmpty ? nil : removedJobs,
                    directions: directions.isEmpty ? nil : .init(additionalProperties: directions),
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
            case .undocumented(let code, let body):
                recipe = nil
                errorMessage = await EngineErrorDetail.message(from: body) ?? "Could not assemble a recipe (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return }   // superseded by a newer answer
            recipe = nil
            errorMessage = await Self.engineWords(error) ?? error.localizedDescription
        }
    }

    /// A step problem's `allow-cloud` fix: the person says pages may leave this Mac, and the
    /// recipe is proposed again with that answer.
    func allowCloud() async {
        cloudAllowed = true
        await assemble()
    }

    /// The job's registered name, or nil when the registry does not know it
    /// (shown as such, never invented here).
    func job(for step: Components.Schemas.RecipeStep) -> Components.Schemas.JobInfo? {
        jobs[step.job]
    }

    /// Whether a job reads the material into text, as the registry says (`JobInfo.reads_material`,
    /// #5612): the finder's readers are for these steps. False for a job the registry does not know.
    func readsMaterial(_ job: String) -> Bool {
        jobs[job]?.readsMaterial ?? false
    }

    /// What explains a job: its topic in the registry, or nil when the job names
    /// none the registry has (the job's name is shown alone).
    func explanation(ofJob id: String) -> Components.Schemas.TopicInfo? {
        topics.topic(jobs[id]?.topic ?? id)
    }

    /// A job's title: its topic's, else its registered name, else the bare id.
    func title(ofJob id: String) -> String {
        explanation(ofJob: id)?.title ?? jobs[id]?.name ?? id
    }

    /// A step's heading: the title the engine gave it, else its job's title. Never empty, never invented.
    func title(of step: Components.Schemas.RecipeStep) -> String {
        step.title ?? title(ofJob: step.job)
    }

    /// A step's one sentence: the engine's, else its topic's short sentence.
    func sentence(of step: Components.Schemas.RecipeStep) -> String? {
        step.sentence ?? explanation(ofJob: step.job)?.short
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
    /// Start: no recipe step runs on it. With Index, the folder is then tied
    /// through `/api/sync-folders` (`source.onboard.index-ties-the-folder`), so
    /// Index is whole and not only a recorded mode; `tiedFolderPath` names it
    /// for the screen to show. With Keep arranged the folder is tied the same way (as Index, so
    /// nothing moves yet) and its dry run is read and shown with Arrange: the engine arranges a
    /// folder the moment it is kept arranged, so the mode changes only on that yes
    /// (`source.onboard.keep-arranged`, `SyncFolderStore.confirmKeepArranged`).
    func addFolder(_ url: URL, importer: ImportService, syncFolders: SyncFolderStore? = nil) async {
        materialAdded = nil
        tiedFolderPath = nil
        do {
            let ids = try await importer.importFolder(url, mode: ingestMode)
            materialAdded = "\(url.lastPathComponent): \(ids.count) added (\(wayIn.title.lowercased()))."
            if ingestMode == .index, let syncFolders {
                if let tied = await syncFolders.tie(path: url.path) {
                    tiedFolderPath = url.path
                    if keepsArranged, tied.mode != .keepArranged,
                       await syncFolders.proposeKeepArranged(tied.id) == nil {
                        errorMessage = syncFolders.errorMessage
                    }
                } else {
                    errorMessage = syncFolders.errorMessage
                }
            }
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
            rememberOverrides(from: try JSONEncoder().encode(saved))
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

// MARK: - ChangeEventConsumer (#5583)

/// Registered on the project's change stream (`LibraryReference.changeStream`) beside the other stores.
extension RecipeSetupStore: ChangeEventConsumer {
    nonisolated var changeDomains: Set<String> { ["model"] }

    func apply(_ event: ChangeEvent) {
        if event.type == "model.installed" { modelInstalled() }
    }

    /// Events missed while the stream was down may include a finished download: read a shown plan again.
    func resync() async {
        guard startPlan != nil else { return }
        await loadStartPlan()
    }
}
