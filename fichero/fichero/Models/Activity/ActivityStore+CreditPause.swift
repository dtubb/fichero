import Foundation

extension ActivityStore {
    /// A run paused for its provider's credit (`recipes-run.credit.out-of-credit-pauses-and-asks`, #6675) raises its one box:
    /// Continue resumes it through the run's own Resume (the engine checks the provider again), Stop run stops it.
    func askAboutCredit(in jobs: [ActivityJob]) {
        guard let job = creditLedger.newlyPaused(in: jobs).first else { return }
        creditPause = CreditPausePrompt.make(
            job,
            openProviderPage: { self.openProviderPage($0) },
            resume: { Task { _ = await self.setJobPaused(jobId: job.id, paused: false, runThreadId: nil) } },
            stop: { Task { _ = await self.cancelJob(jobId: job.id, runThreadId: nil) } })
    }
}
