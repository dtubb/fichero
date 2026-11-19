import Foundation

extension ActivityStore {
    /// A run paused for its provider's credit (`recipes-run.credit.out-of-credit-pauses-and-asks`, #6675) raises its one box:
    /// Continue resumes it through the run's own Resume (the engine checks the provider again), Stop run stops it.
    func askAboutCredit(in jobs: [ActivityJob]) {
        guard creditPause == nil, let job = creditLedger.nextToAsk(in: jobs) else { return }
        // One dialogue for the cause: Continue and Stop Run act on every run paused for it when the button is pressed (a run
        // that paused a poll later is included), then the next cause, if any, is asked.
        let held = { CreditPauseLedger.sameCause(as: job, in: self.backgroundJobs).map(\.id) }
        creditPause = CreditPausePrompt.make(
            job,
            openProviderPage: { self.openProviderPage($0) },
            resume: {
                Task {
                    for id in held() { _ = await self.setJobPaused(jobId: id, paused: false, runThreadId: nil) }
                    self.askAboutCredit(in: self.backgroundJobs)
                }
            },
            stop: {
                Task {
                    for id in held() { _ = await self.cancelJob(jobId: id, runThreadId: nil) }
                    self.askAboutCredit(in: self.backgroundJobs)
                }
            })
    }
}
