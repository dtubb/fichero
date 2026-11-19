import Foundation

/// One dialogue per cause and provider, never one per run or page (`runner.ask.one-dialogue-per-cause`): while any run stays
/// paused for a provider's credit the cause has been asked about; once none is, the next credit pause asks anew.
struct CreditPauseLedger {
    private var asked: Set<String> = []

    /// The runs of `jobs` that newly meet a provider's credit pause, one per provider; what is no longer paused for credit is forgotten.
    mutating func newlyPaused(in jobs: [ActivityJob]) -> [ActivityJob] {
        let paused = jobs.filter(CreditPausePrompt.isCreditPause)
        let keys = Set(paused.map(Self.key))
        asked.formIntersection(keys)
        return paused.filter { asked.insert(Self.key($0)).inserted }  // two runs meeting the cause in one poll are one dialogue
    }

    /// The one run to ask about now: the first paused for a cause not yet asked about, marked asked only when returned. A second
    /// cause (another provider) stays unasked until a later call, so its dialogue is raised once the first is answered.
    mutating func nextToAsk(in jobs: [ActivityJob]) -> ActivityJob? {
        let paused = jobs.filter(CreditPausePrompt.isCreditPause)
        asked.formIntersection(Set(paused.map(Self.key)))
        guard let job = paused.first(where: { !asked.contains(Self.key($0)) }) else { return nil }
        asked.insert(Self.key(job))
        return job
    }

    /// Every run of `jobs` paused for the same cause and provider as `job`, `job` included: the one dialogue answers them all.
    static func sameCause(as job: ActivityJob, in jobs: [ActivityJob]) -> [ActivityJob] {
        jobs.filter { CreditPausePrompt.isCreditPause($0) && key($0) == key(job) }
    }

    private static func key(_ job: ActivityJob) -> String { "\(job.failure?.kind ?? "")|\(job.failure?.provider ?? "")" }
}
