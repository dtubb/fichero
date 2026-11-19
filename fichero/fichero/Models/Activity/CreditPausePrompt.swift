import Foundation

/// The one dialogue of a run paused because its provider is out of credit or at a credit limit
/// (`recipes-run.credit.out-of-credit-pauses-and-asks`, #6675). The engine pauses the run and says so in the run's failure
/// (kind `no-credit`, Continue first); this turns that paused row into the box: which provider, out of credit or at its limit
/// (the engine's words), what is paused and how far, and three buttons.
enum CreditPausePrompt {
    /// A run paused for credit: paused, and its failure is the engine's `no-credit` with Continue as its first action.
    nonisolated static func isCreditPause(_ job: ActivityJob) -> Bool {
        job.state == .paused && job.failure?.kind == "no-credit" && job.failure?.primaryAction == "resume"
    }

    /// Where a provider's credit is topped up or its limits are set; nil for a provider not listed (the button is then left out).
    nonisolated static func providerPage(_ provider: String?) -> URL? {
        switch provider?.lowercased() {
        case "openrouter": URL(string: "https://openrouter.ai/credits")
        case "openai": URL(string: "https://platform.openai.com/settings/organization/billing/overview")
        case "anthropic": URL(string: "https://console.anthropic.com/settings/billing")
        case "google": URL(string: "https://aistudio.google.com/plan_information")
        default: nil
        }
    }

    /// The box for a paused `job`: the engine's words, what is paused (the run's name and its pages done of the total), then
    /// Open provider page (when the provider's page is known), Continue and Stop run.
    static func make(
        _ job: ActivityJob,
        openProviderPage: @escaping (URL) -> Void,
        resume: @escaping () -> Void,
        stop: @escaping () -> Void
    ) -> FailureAlertPrompt {
        let failure = job.failure
        let paused = job.total > 0
            ? "Paused: \(job.name), \(job.current) of \(job.total) pages done, the rest waiting."
            : "Paused: \(job.name)."
        var buttons: [(label: String, action: () -> Void)] = []
        if let page = providerPage(failure?.provider) {
            buttons.append(("Open \(failure?.provider ?? "Provider") Page", { openProviderPage(page) }))
        }
        buttons.append(("Continue", resume))
        buttons.append(("Stop Run", stop))
        return FailureAlertPrompt(
            title: "\(failure?.provider ?? "The provider") needs credit",
            message: [failure?.words ?? "", paused, failure?.fix ?? ""].filter { !$0.isEmpty }.joined(separator: "\n\n"),
            fixes: buttons.enumerated().map { FailureAlertPrompt.Fix(id: $0.offset, label: $0.element.label, action: $0.element.action) })
    }
}
