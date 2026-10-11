import Foundation

/// One candidate's go at a stage's sample pages (#5668, `source.onboard.stages.compares-candidates`): the bake-off
/// row's fields (its card, name, where it runs, its measures and cost) with its own result on the samples, in the shape
/// the stage's try answers. Read from the try's `candidates`; a column of the A/B/C comparison.
struct StageCandidate: Decodable, Equatable, Identifiable {
    struct Cost: Decodable, Equatable {
        let value: Double?
        let basis: String?
    }

    let card: String
    let name: String?
    let runsOn: String?
    let local: Bool?
    /// Character error rate against a checked reading, 0–1; nil when nothing was checked.
    let cer: Double?
    /// Agreement with the other candidates, 0–1, when there is no checked reading.
    let agreement: Double?
    let seconds: Double?
    let costUsd: Cost?
    /// Why it has no score, in the engine's words.
    let why: String?
    let perPage: [SetupStageTryResult.Page]?
    let names: [SetupStageTryResult.Name]?

    var id: String { card }

    enum CodingKeys: String, CodingKey {
        case card, name, local, cer, agreement, seconds, why, names
        case runsOn = "runs_on"
        case costUsd = "cost_usd"
        case perPage = "per_page"
    }

    /// Its column's title: its name, else its card.
    var title: String { name ?? card }

    /// Runs on this Mac: free.
    var runsHere: Bool { local == true || (runsOn ?? "").hasPrefix("this-mac") }

    /// What it measured, in words, for under its column: how good (character errors, else agreement), how long,
    /// and what it costs ("free, on this Mac" or the cloud's price).
    var measures: [String] {
        var said: [String] = []
        if let cer {
            said.append(cer.formatted(.percent.precision(.fractionLength(1))) + " character errors")
        } else if let agreement {
            said.append(agreement.formatted(.percent.precision(.fractionLength(0))) + " agreement")
        } else if let why {
            said.append(why)
        }
        if let seconds { said.append("\(Int(seconds.rounded())) s") }
        if runsHere {
            said.append("free, on this Mac")
        } else if let value = costUsd?.value {
            let price = value.formatted(.currency(code: "USD"))
            said.append(costUsd?.basis == "estimate" ? "about \(price)" : price)
        } else {
            said.append("price not known")
        }
        return said
    }

    /// Its result on the samples, as its column's picture plays it; nil when it made nothing.
    var showcase: StageShowcase? {
        StageShowcaseSource.own(pages: perPage ?? [], names: names ?? [])
    }

    /// The columns to show: the engine's candidates, at most three; one column when there is one.
    static func columns(_ candidates: [StageCandidate]?) -> [StageCandidate] {
        Array((candidates ?? []).prefix(3))
    }
}

extension RecipeSetupStore {
    /// The recipe's step that does one of these jobs (a stage's), for Use This.
    func stepId(forJobs jobs: [String]) -> String? {
        recipe?.steps.first { jobs.contains($0.job) }?.id
    }
}
