import FicheroAPIClient
import Foundation
import OSLog

/// Setup's model questions answered by the model finder (#5619, `source.find.choose-a-model-opens-the-finder`): a
/// step's Choose a model…, Download a model… and Use a cloud model… open the finder for THAT step's job, with the
/// project's scripts, languages and first material, in Set Up… › Ready (the step's row, and the same step under
/// Will not run). Kept beside `RecipeSetupStore` so the store's own file stays setup's.
extension RecipeSetupStore {
    /// The fixes the model finder answers: choosing a model, downloading one, or choosing a cloud one (the finder
    /// lists every place a model runs, with where in words). Letting pages leave and accepting a licence are
    /// answered elsewhere (the cloud question; the card's licence).
    nonisolated static let finderFixes: Set<String> = ["choose-model", "download", "choose-cloud"]

    nonisolated static func fixOpensFinder(_ fix: String) -> Bool {
        finderFixes.contains(fix)
    }

    /// How a step that runs no model works, in the engine's words (`StartRun.how`, #5791); nil for any other.
    func how(ofStep step: String) -> String? {
        startPlan?.runs.first { $0.steps.contains(step) }?.how.flatMap { $0.isEmpty ? nil : $0 }
    }

    /// The job of a step in the recipe on screen, by its id; nil for a step the recipe does not have.
    func job(ofStepId step: String) -> String? {
        recipe?.steps.first { $0.id == step }?.job
    }

    /// What the finder asks for a step's job: the project's scripts and languages and its first material.
    func finderQuery(job: String, step: String? = nil) -> ModelFinderStore.Query {
        .init(job: job, scripts: scripts, languages: languages, material: materials.first ?? "handwriting", step: step,
              cloudAllowed: cloudAllowed)
    }
}

// Start's words in Ready (#5660).
extension RecipeSetupStore {
    /// Why Start cannot be pressed yet, in words, for the button's help; nil when it can (#5660 item 2: every Set Up
    /// button acts, or is disabled with its reason).
    var startDisabledReason: String? {
        guard !canStart else { return nil }
        if isAddingMaterial { return "Fichero is still adding your material; Start waits for it." }
        guard let plan = startPlan else { return "Fichero is still planning what Start would run." }
        if let first = plan.refusals.first { return "Start waits: \(first)" }
        return "Nothing in this plan runs yet: every step is skipped (see why above)."
    }

    /// The plan's words for steps that wait for a model already downloading ("... which is downloading (1.2 GB of
    /// 5.6 GB): they run when it lands"), shown in place of a refusal (#5660).
    var waitingForDownloads: [String] { startPlan?.waiting ?? [] }

    /// The waiting lines paired with the downloads under way they were written from, in the engine's order
    /// (`start.py`: `waiting` is one sentence per download marked `downloading`), each with the step ids it holds up.
    private var waitingByStep: [(line: String, steps: Set<String>)] {
        guard let plan = startPlan else { return [] }
        let downloading = (plan.downloads ?? []).filter { $0.downloading == true }
        return zip(plan.waiting ?? [], downloading).map { (line: $0, steps: Set($1.steps)) }
    }

    /// The waiting lines that hold up this step (shown in its box on Ready, #5840).
    func waitingForDownloads(inStep stepId: String) -> [String] {
        waitingByStep.filter { $0.steps.contains(stepId) }.map(\.line)
    }

    /// The waiting lines that name none of these steps (shown once, with the plan-wide lines).
    func waitingForDownloads(notInSteps stepIds: Set<String>) -> [String] {
        let paired = waitingByStep
        let unpaired = Array(waitingForDownloads.dropFirst(paired.count))
        return paired.filter { $0.steps.isDisjoint(with: stepIds) }.map(\.line) + unpaired
    }
}

extension RecipeStepsView {
    /// Where a fix goes: the model finder for the step, the step's licence to review and accept (#5660), or
    /// setup's handler (letting pages leave; without a project, Settings › AI Models).
    enum FixRoute: Equatable { case finder, licence, setup }

    static func fixRoute(_ fix: String, hasProject: Bool) -> FixRoute {
        guard hasProject else { return .setup }
        if RecipeSetupStore.fixOpensFinder(fix) { return .finder }
        return fix == "accept-licence" ? .licence : .setup
    }
}

// A reopened project's languages and scripts by name (2026-10-11, the onboarding screenshots): the saved answers
// keep tags ("es", "Latn"); without this the tokens read "es" until the person searched again.
extension RecipeSetupStore {
    /// Name every saved language and script the field would otherwise show as a bare code, from the engine's
    /// own search (its exact match on the code). Quiet: the answers themselves loaded, so a failed lookup leaves
    /// the code showing, is logged, and never becomes setup's error.
    func resolveNames() async {
        let said = errorMessage
        for code in languages where name(of: code) == code {
            if let match = await searchLanguages(code).first(where: { $0.code == code }) { add(match, toScripts: false) }
        }
        for code in scripts where name(of: code) == code {
            if let match = await searchScripts(code).first(where: { $0.code == code }) { add(match, toScripts: true) }
        }
        if errorMessage != said {
            Logger(subsystem: "app.fichero.fichero", category: "RecipeSetup")
                .info("Naming the saved languages and scripts failed; their codes show: \(self.errorMessage ?? "", privacy: .public)")
            errorMessage = said
        }
    }
}

// What the last run left undone, under the step in Ready (#5616).
extension RecipeSetupStore {
    /// "Not run last time (the run was stopped before this step); runs again", from the plan's run that carries the
    /// step (`last_run`, `last_why`); nil when the last run did it, or it never ran.
    func lastRunWords(stepId: String) -> String? {
        guard let run = startPlan?.runs.first(where: { $0.steps.contains(stepId) && $0.lastRun != nil }),
              let outcome = run.lastRun else { return nil }
        let said = outcome.prefix(1).uppercased() + outcome.dropFirst()
        let why = run.lastWhy.map { " (\($0))" } ?? ""
        return "\(said) last time\(why); runs again"
    }
}
