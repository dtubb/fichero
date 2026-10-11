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

    /// The job of a step in the recipe on screen, by its id; nil for a step the recipe does not have.
    func job(ofStepId step: String) -> String? {
        recipe?.steps.first { $0.id == step }?.job
    }

    /// What the finder asks for a step's job: the project's scripts and languages and its first material.
    func finderQuery(job: String, step: String? = nil) -> ModelFinderStore.Query {
        .init(job: job, scripts: scripts, languages: languages, material: materials.first ?? "handwriting", step: step)
    }
}

// Start's words in Ready (#5660).
extension RecipeSetupStore {
    /// Why Start cannot be pressed yet, in words, for the button's help; nil when it can (#5660 item 2: every Set Up
    /// button acts, or is disabled with its reason).
    var startDisabledReason: String? {
        guard !canStart else { return nil }
        guard let plan = startPlan else { return "Fichero is still planning what Start would run." }
        if let first = plan.refusals.first { return "Start waits: \(first)" }
        return "Nothing in this plan runs yet: every step is skipped (see why above)."
    }

    /// The plan's words for steps that wait for a model already downloading ("... which is downloading (1.2 GB of
    /// 5.6 GB): they run when it lands"), shown in place of a refusal (#5660).
    var waitingForDownloads: [String] { startPlan?.waiting ?? [] }
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
