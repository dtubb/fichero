import FicheroAPIClient
import Foundation

extension StageCandidateChoice {
    /// The model a stage page opens with ticked (#6119, `source.onboard.stages.model-ticked-by-default`): the only
    /// model, or the best-ranked one: the first the engine would compare, else the first. A reader made for another
    /// period and a model that won't fit this Mac are never ticked for the person. Empty: nothing fits to tick.
    nonisolated static func preselected(_ candidates: [Components.Schemas.ModelCandidate]) -> [String] {
        let usable = candidates.filter {
            $0.otherPeriod != true && CandidateFit.of($0, in: candidates)?.isGreyed != true
        }
        guard let best = usable.first(where: { $0.comparedByDefault == true }) ?? usable.first else { return [] }
        return [best.id]
    }
}
