import FicheroAPIClient
import SwiftUI

/// Which of the step's candidates Compare on These Pages runs side by side (#5668,
/// `source.onboard.stages.compares-candidates`): the step's own list from the per-step finder, up to three ticked.
/// With none ticked, the engine compares the step's own model with its next one or two.
struct StageCandidateChooser: View {
    let candidates: [Components.Schemas.ModelCandidate]
    @Binding var chosen: [String]
    /// Uses a smaller build the engine names for a model that won't fit (#5641), for the stage's step.
    var useSmaller: ((CandidateFit.Smaller) -> Void)?

    /// What can do the step, said on the page where a stage has only a few that can (#5838): Find Lines lists line
    /// finders alone, and a cloud vision model (a hand-added Opus, say) is not one.
    static func whoDoes(stageId: String) -> String? {
        guard stageId == "find-lines" else { return nil }
        return "Kraken finds the lines of handwriting and print; Apple Vision finds the lines of print and typed pages "
            + "only. Cloud vision models can't find lines yet, so they are not offered here."
    }

    /// How many of the step's candidates are offered here; the finder lists the rest.
    static let offered = 8

    /// The list split by fit to the project's period (#5808): the readers made for it (or for none stated), then the
    /// ones made for another period, which the page lists apart under "Other periods".
    nonisolated static func split(_ candidates: [Components.Schemas.ModelCandidate])
        -> (fitting: [Components.Schemas.ModelCandidate], otherPeriods: [Components.Schemas.ModelCandidate]) {
        (candidates.filter { $0.otherPeriod != true }, candidates.filter { $0.otherPeriod == true })
    }

    /// The names Compare runs when none is ticked, as the engine chose them (`compared_by_default`).
    nonisolated static func defaultNames(_ candidates: [Components.Schemas.ModelCandidate]) -> [String] {
        candidates.filter { $0.comparedByDefault == true }.map(\.name)
    }

    /// Whether a row can be ticked now: up to three, and never a model that won't fit this Mac (greyed with its
    /// reason, #5641); a row already ticked can always be unticked.
    nonisolated static func canTick(_ candidate: Components.Schemas.ModelCandidate, chosen: [String],
                        in list: [Components.Schemas.ModelCandidate]) -> Bool {
        if chosen.contains(candidate.id) { return true }
        if CandidateFit.of(candidate, in: list)?.isGreyed == true { return false }
        return chosen.count < StageCandidateChoice.most
    }

    var body: some View {
        let groups = Self.split(candidates)
        VStack(alignment: .leading, spacing: 6) {
            Text("Models for your pages").font(.headline)
            Text(intro)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(groups.fitting.prefix(Self.offered), id: \.id) { row($0) }
            if !groups.otherPeriods.isEmpty {
                // No disclosure in setup (#5481): the other periods' models are listed under their own line.
                Text("Other periods (\(groups.otherPeriods.count))").font(.callout)
                ForEach(groups.otherPeriods.prefix(Self.offered), id: \.id) { row($0) }
            }
        }
        .accessibilityIdentifier("setup.stage.compareChooser")
    }

    /// What Compare says it will do: the models it names, never "the next one or two".
    private var intro: String {
        let names = Self.defaultNames(candidates)
        let base = "Tick up to three to compare on these pages."
        return names.isEmpty
            ? base + " With none ticked, Fichero compares the step's own model with the finder's next runnable ones."
            : base + " With none ticked, Fichero compares: " + names.joined(separator: ", ") + "."
    }

    /// One candidate: its whole name (wrapped, never cut), where it runs, a link to its page, and its fit.
    @ViewBuilder
    private func row(_ candidate: Components.Schemas.ModelCandidate) -> some View {
        let fit = CandidateFit.of(candidate, in: candidates)
        VStack(alignment: .leading, spacing: 2) {
            Toggle(isOn: Binding(
                get: { chosen.contains(candidate.id) },
                set: { _ in chosen = StageCandidateChoice.toggle(candidate.id, in: chosen) }
            )) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(candidate.shortName ?? candidate.name).fixedSize(horizontal: false, vertical: true).help(candidate.name)
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(candidate.availabilityWords).font(.caption).foregroundStyle(.secondary)
                        if let link = candidate.link, let url = URL(string: link) {
                            Link("Page", destination: url).font(.caption)
                        }
                    }
                }
            }
            #if os(macOS)
            .toggleStyle(.checkbox)
            #endif
            .disabled(!Self.canTick(candidate, chosen: chosen, in: candidates))
            .help(fit?.line ?? "")
            if let fit {
                CandidateFitLabel(fit: fit, useSmaller: useSmaller)
                    .padding(.leading, 20)
            }
        }
    }
}

#Preview("Choose who to compare") {
    @Previewable @State var chosen = ["kraken-catmus"]
    let json = """
    [{"id":"kraken-catmus","name":"Kraken (CATMuS Medieval)","source":"rules","offered_because":"","pin":null,"jobs":[],
      "open_licence":true,"size":"16 MB","measured":false,"in_recipe_rules":true,"runs_where":"this-mac",
      "availability":"installed","availability_words":"on this Mac"},
     {"id":"apple-vision","name":"Apple Vision","source":"rules","offered_because":"","pin":null,"jobs":[],
      "open_licence":false,"size":"built in","measured":false,"in_recipe_rules":true,"runs_where":"this-mac",
      "availability":"installed","availability_words":"built into macOS"}]
    """
    let candidates = (try? JSONDecoder().decode([Components.Schemas.ModelCandidate].self, from: Data(json.utf8))) ?? []
    StageCandidateChooser(candidates: candidates, chosen: $chosen)
        .padding()
        .frame(width: 420)
}
