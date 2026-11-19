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

    private static func key(_ job: ActivityJob) -> String { "\(job.failure?.kind ?? "")|\(job.failure?.provider ?? "")" }
}
