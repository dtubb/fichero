import Foundation

extension ActivityStore {
    /// A run paused for its provider's credit (`recipes-run.credit.out-of-credit-pauses-and-asks`, #6675) raises its one box:
    /// Continue resumes it through the run's own Resume (the engine checks the provider again), Stop run stops it.
    func askAboutCredit(in jobs: [ActivityJob]) {
        guard let job = creditLedger.newlyPaused(in: jobs).first else { return }
        // One dialogue for the cause: Continue and Stop Run act on every run it holds, so none is left paused unasked.
        let held = CreditPauseLedger.sameCause(as: job, in: jobs).map(\.id)
        creditPause = CreditPausePrompt.make(
            job,
            openProviderPage: { self.openProviderPage($0) },
            resume: { Task { for id in held { _ = await self.setJobPaused(jobId: id, paused: false, runThreadId: nil) } } },
            stop: { Task { for id in held { _ = await self.cancelJob(jobId: id, runThreadId: nil) } } })
    }
}
