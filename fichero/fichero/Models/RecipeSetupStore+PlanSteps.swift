import FicheroAPIClient
import Foundation

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
