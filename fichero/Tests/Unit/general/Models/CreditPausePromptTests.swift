@testable import Fichero
import Foundation
import Testing

/// `recipes-run.credit.out-of-credit-pauses-and-asks` (#6675): a run paused for credit raises one box with Open provider page,
/// Continue and Stop run; a rate-limit pause raises none; the same pause is asked once.
@Suite("Credit pause prompt")
struct CreditPausePromptTests {
    private func job(
        _ id: String = "run-1", state: ActivityJob.State = .paused, kind: String = "no-credit", first: String = "resume",
        provider: String? = "OpenRouter"
    ) -> ActivityJob {
        var job = ActivityJob(id: id, taskType: "workflow", name: "Read the page", current: 12, total: 37, state: state)
        job.failure = ActivityJob.Failure(kind: kind, words: "OpenRouter is out of credit, so the run is paused.",
                                          fix: "Add credit, then Continue.",
                                          actions: [first, "open-settings"], provider: provider)
        return job
    }

    @Test("a paused no-credit run is a credit pause; a rate-limit pause and a failed run are not")
    func recognised() {
        #expect(CreditPausePrompt.isCreditPause(job()))
        #expect(!CreditPausePrompt.isCreditPause(job(kind: "rate-limited")))
        #expect(!CreditPausePrompt.isCreditPause(job(state: .failed, first: "open-settings")))
    }

    @Test("the box names what is paused and has Open provider page, Continue and Stop Run")
    func buttons() {
        var done: [String] = []
        let prompt = CreditPausePrompt.make(job(), openProviderPage: { done.append($0.host ?? "") },
                                            resume: { done.append("continue") }, stop: { done.append("stop") })
        #expect(prompt.fixes.map(\.label) == ["Open OpenRouter Page", "Continue", "Stop Run"])
        #expect(prompt.message.contains("OpenRouter is out of credit"))
        #expect(prompt.message.contains("12 of 37 pages done"))
        prompt.fixes.forEach { $0.action() }
        #expect(done == ["openrouter.ai", "continue", "stop"])
    }

    @Test("one box per run and provider: the same pause is not asked again, a new pause after Continue is")
    func askedOnce() {
        var ledger = CreditPauseLedger()
        #expect(ledger.newlyPaused(in: [job()]).count == 1)
        #expect(ledger.newlyPaused(in: [job()]).isEmpty)
        #expect(ledger.newlyPaused(in: [job(state: .running)]).isEmpty)
        #expect(ledger.newlyPaused(in: [job()]).count == 1)
    }

    @Test("two runs meeting the same provider's pause are one dialogue; another provider is its own")
    func oneDialoguePerCause() {
        var ledger = CreditPauseLedger()
        #expect(ledger.newlyPaused(in: [job("run-1"), job("run-2")]).count == 1)
        #expect(ledger.newlyPaused(in: [job("run-1"), job("run-2"), job("run-3")]).isEmpty)
        #expect(ledger.newlyPaused(in: [job("run-1"), job("run-4", provider: "OpenAI")]).count == 1)
    }
}
