import FicheroAPIClient
import Foundation

/// What a person can do in place when the cloud spend caps stop (or would stop) a run (#6295, `ai.where.cloud-spend-cap`):
/// the engine's `cloud_cap` line read as words and offers. The amounts are the engine's (`needed_cap_usd`,
/// `needed_project_cap_usd`, `fewer_pages`): the best estimate, no margin; nothing is worked out here. Pure, for the tests.
struct CloudCapFix: Equatable {
    /// "Raise the monthly cap to $18.00": the cap to set, in dollars.
    struct Raise: Equatable {
        let usd: Double
        let title: String
    }

    /// Set the monthly cap, when the estimate is over what it leaves.
    let monthly: Raise?
    /// Set the project's total cap, when the estimate is over what it leaves.
    let project: Raise?
    /// Run only this many of the first pages (Finder order), when that fits what the caps leave.
    let firstPages: Int?
    /// The reason in plain words; nil when the run is not over a cap.
    let reason: String?

    var isOffered: Bool { monthly != nil || project != nil }

    nonisolated init(_ line: Components.Schemas.CloudCapLine) {
        guard line.over, let estimate = line.estimateUsd else {
            monthly = nil
            project = nil
            firstPages = nil
            reason = nil
            return
        }
        monthly = line.overMonth == true ? line.neededCapUsd.map { Raise(usd: $0, title: "Raise the monthly cap to \(Self.usd($0))") } : nil
        project = line.overProject == true
            ? line.neededProjectCapUsd.map { Raise(usd: $0, title: "Raise the project cap to \(Self.usd($0))") } : nil
        firstPages = line.fewerPages
        var parts: [String] = []
        if line.overMonth == true {
            parts.append("the monthly cap (\(Self.usd(line.capUsd))) leaves \(Self.usd(line.remainingUsd))")
        }
        if line.overProject == true, let cap = line.projectCapUsd {
            parts.append("the project's total cap (\(Self.usd(cap))) leaves \(Self.usd(max(0, cap - (line.projectSpentUsd ?? 0))))")
        }
        reason = "This run is estimated at \(Self.usd(estimate)), more than " + parts.joined(separator: " and ") + "."
    }

    nonisolated static func usd(_ value: Double) -> String { value.formatted(.currency(code: "USD")) }

    /// "Run the first 40 pages": the engine's count of the first pages that fit.
    nonisolated static func firstPagesTitle(_ count: Int) -> String {
        count == 1 ? "Run the first page" : "Run the first \(count) pages"
    }

    /// The estimate's basis, a line per run: its pages, what it is priced at, and its cost, so the figure beside the cap can be
    /// checked ("Read lines: 120 pages · the model's listed rate · $2.71"). `title` names a run's steps.
    nonisolated static func basis(of estimate: Components.Schemas.StartEstimate, title: (String) -> String) -> [String] {
        estimate.runs.map { run in
            let name = run.steps.map(title).joined(separator: ", ")
            var parts = ["\(run.pages) \(run.pages == 1 ? "page" : "pages")"]
            if let calls = run.callsPerPage, calls > 1 { parts.append("\(calls) calls a page") }
            parts.append(run.basis ?? (run.costUsd == nil ? "unpriced" : "estimated"))
            parts.append(run.costUsd.map(Self.usd) ?? "price unknown")
            return "\(name): " + parts.joined(separator: " · ")
        }
    }

    /// Whether a plan refusal is the cap's (`_cap_refusals`): the cap row says it, with its fixes, so the list does not.
    nonisolated static func isCapRefusal(_ refusal: String) -> Bool {
        refusal.hasPrefix("This run is estimated at US$") && refusal.contains(" cap ")
    }

    /// Whether words are about a spend cap: the plan's refusal, the 422 a refused Start answers with it, or a run's own reason
    /// when a call was refused at the cap (`spend.py`: "cloud spend is capped", "capped at").
    nonisolated static func mentionsCap(_ words: String?) -> Bool {
        guard let words else { return false }
        return isCapRefusal(words) || words.contains("Start is refused: This run is estimated at US$") && words.contains(" cap ")
            || words.contains("cloud spend is capped")
    }
}
