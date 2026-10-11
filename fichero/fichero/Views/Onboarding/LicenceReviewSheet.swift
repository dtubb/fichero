import FicheroAPIClient
import SwiftUI

/// Set Up… › Review the licence… for one step (#5660 item 2): the models that fit the step but carry a licence
/// that is not open, each with its licence named and a link to read it, and Accept and Use for This Step.
/// Accepting is the engine's existing deliberate choice of a model (`POST /api/recipes/project/steps/use-candidate`,
/// `RecipeSetupStore.useCandidate`): the step takes the model as the project's override, saved and audited, and a
/// licence that is not open is accepted by that press (`source.onboard.auto.installed-model-first`, #5612).
struct LicenceReviewSheet: View {
    let project: LibraryManager.LibraryReference
    let setup: RecipeSetupStore
    let step: RecipeStepsView.FinderStep
    let onDone: () -> Void

    @State private var accepting: String?

    private var finder: ModelFinderStore { project.modelFinderStore }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Review the Licence for \(setup.title(ofStepId: step.id))").font(.headline)
            Text("These models fit this step, but their licence is not open. Read it, and accept it only if your use fits.")
                .font(.callout)
                .foregroundStyle(.secondary)
            let shown = Self.licensed(finder.candidates, refused: Self.refusedForLicence(setup, step: step.id))
            if finder.isLoading {
                ProgressView("Reading the models for this step…").controlSize(.small)
            } else if shown.isEmpty {
                Text("No model for this step is waiting on a licence. Choose another model with Find a Reader….")
                    .font(.callout)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(shown, id: \.id) { candidate in
                        row(candidate)
                    }
                }
            }
            if let message = setup.errorMessage {
                Label(message, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
            HStack {
                Spacer()
                Button("Cancel", action: onDone).keyboardShortcut(.cancelAction)
            }
        }
        .padding()
        .frame(minWidth: 460, minHeight: 320)
        .task { await finder.load(setup.finderQuery(job: step.job)) }
    }

    private func row(_ candidate: Components.Schemas.ModelCandidate) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(candidate.name).font(.body.weight(.medium))
            Text("Licence: \(Self.licenceName(candidate))").font(.callout)
            HStack {
                if let url = Self.licenceURL(candidate.licence) {
                    Link("Read the Licence", destination: url)
                }
                Spacer()
                Button("Accept and Use for This Step") {
                    accepting = candidate.id
                    Task {
                        await setup.useCandidate(candidate, forStep: step.id)
                        accepting = nil
                        if setup.errorMessage == nil { onDone() }
                    }
                }
                .disabled(accepting != nil)
            }
            .controlSize(.small)
        }
        .padding(8)
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 6))
    }

    /// The cards the rules refused for this step because their licence is not open (`StepProblem.refused`).
    static func refusedForLicence(_ setup: RecipeSetupStore, step: String) -> [String] {
        let refused = setup.recipe?.steps.first { $0.id == step }?.problem?.refused ?? []
        return refused.filter { $0.why.contains("licence") }.map(\.card)
    }

    /// The candidates to review: those whose licence is not open, the ones the rules refused for it first; every
    /// one that is not open when the rules named none the finder lists.
    static func licensed(_ candidates: [Components.Schemas.ModelCandidate],
                         refused: [String]) -> [Components.Schemas.ModelCandidate] {
        let closed = candidates.filter { !$0.openLicence }
        let named = closed.filter { refused.contains($0.id) }
        return named.isEmpty ? closed : named
    }

    static func licenceName(_ candidate: Components.Schemas.ModelCandidate) -> String {
        let licence = candidate.licence ?? ""
        return licence.isEmpty ? "not stated" : licence
    }

    /// The licence's text, for a licence named by its SPDX identifier ("cc-by-nc-4.0"); nil for one in words.
    static func licenceURL(_ licence: String?) -> URL? {
        guard let licence, !licence.isEmpty,
              licence.allSatisfy({ $0.isLetter || $0.isNumber || $0 == "-" || $0 == "." || $0 == "+" })
        else { return nil }
        return URL(string: "https://spdx.org/licenses/\(licence).html")
    }
}
