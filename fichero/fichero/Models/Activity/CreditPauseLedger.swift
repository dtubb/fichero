import Foundation

/// One dialogue per provider per run, never one per page: a run asked about is not asked again while it stays paused for
/// that provider; once it goes on, its next credit pause asks anew.
struct CreditPauseLedger {
    private var asked: Set<String> = []

    /// The runs of `jobs` newly paused for a provider's credit, once each; what is no longer paused for credit is forgotten.
    mutating func newlyPaused(in jobs: [ActivityJob]) -> [ActivityJob] {
        let paused = jobs.filter(CreditPausePrompt.isCreditPause)
        let keys = Set(paused.map(Self.key))
        asked.formIntersection(keys)
        return paused.filter { asked.insert(Self.key($0)).inserted }
    }

    private static func key(_ job: ActivityJob) -> String { "\(job.id)|\(job.failure?.provider ?? "")" }
}
