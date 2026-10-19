import FicheroAPIClient
import SwiftUI

/// Set Up… › Review the licence… for one step (#5660 item 2): the models that fit the step but carry a licence
/// that is not open, each with its licence named and a link to read it, and Accept and Use for This Step.
/// Accepting is the engine's existing deliberate choice of a model (`POST /api/recipes/project/steps/use-candidate`,
/// `RecipeSetupStore.useCandidate`): the step takes the model as the project's override, saved and audited, and a
/// licence that is not open is accepted by that press (`source.onboard.auto.installed-model-first`, #5612).
struct LicenceReviewSheet: View {
    /// The project's model finder (`LibraryReference.modelFinderStore`), which lists the step's models.
    let finder: ModelFinderStore
    let setup: RecipeSetupStore
    let step: RecipeStepsView.FinderStep
    let onDone: () -> Void
    /// Read the step's models on appear; off for a preview or a screenshot, whose finder is already filled.
    var loadsCandidates = true

    @State private var accepting: String?
    /// The one clear acceptance (section 7d, `source.onboard.models.licence-accepted-once`): the person ticks that
    /// they accept this model's licence, then Accept and Use for This Step works.
    @State private var accepted: Set<String> = []

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Review the Licence for \(setup.title(ofStepId: step.id))").font(.headline)
            Text("These models fit this step, but each comes with conditions on use. Read them, and accept it only if your use fits.")
                .font(.callout)
                .foregroundStyle(.secondary)
            let shown = Self.licensed(finder.candidates, refused: Self.refusedForLicence(setup, step: step.id))
            if finder.isLoading {
                ProgressView("Reading the models for this step…").controlSize(.small)
            } else if shown.isEmpty {
                Text("No model for this step is waiting on a licence. Choose another model with Find a Reader….")
                    .font(.callout)
            }
            List(shown, id: \.id) { candidate in
                row(candidate)
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
        // The sheet is its own decision: a presenting row that was disabled (while the plan was being proposed)
        // left Accept and Use disabled with it (Daniel, 2026-10-11).
        .environment(\.isEnabled, true)
        .task {
            if loadsCandidates { await finder.load(setup.finderQuery(job: step.job)) }
        }
    }

    private func row(_ candidate: Components.Schemas.ModelCandidate) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(candidate.name).font(.body.weight(.medium))
            Text("Licence: \(Self.licenceName(candidate))").font(.callout)
            Toggle("I accept the \(Self.licenceName(candidate)) licence for this project", isOn: Binding(
                get: { accepted.contains(candidate.id) },
                set: { isOn in if isOn { accepted.insert(candidate.id) } else { accepted.remove(candidate.id) } }
            ))
            .setupCheckbox()
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
                .disabled(!Self.canAccept(accepted: accepted.contains(candidate.id), accepting: accepting))
            }
            .controlSize(.small)
        }
        .padding(.vertical, 4)
    }

    /// Accept and Use works once its licence is ticked as accepted, and not while an acceptance is being kept.
    static func canAccept(accepted: Bool, accepting: String?) -> Bool { accepted && accepting == nil }

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

extension ModelFinderStore {
    /// A step's models as the engine lists them, for the licence review's preview and screenshots: one open, one
    /// held back for its licence (`agpl-3.0`), as in the maintainer's Find regions step of 2026-10-10.
    static let licencePreviewList: Components.Schemas.ModelCandidateList? = {
        let json = """
        {"job":"find-regions","count":2,"items":[
          {"id":"yolo:hf/fichero/regions-open@1","name":"Page regions (open)","source":"shipped",
           "offered_because":"a card that ships with Fichero","pin":{"hf":"fichero/regions-open"},
           "jobs":["find-regions"],"open_licence":true,"size":"0.05 GB","size_gb":0.05,
           "measured":"unmeasured on your pages until a bake-off measures it","in_recipe_rules":true,
           "runs_where":"this_mac","availability":"ships","availability_words":"Available"},
          {"id":"yolo:hf/ultralytics/yolov8-layout@main","name":"YOLOv8 document layout","source":"hugging-face",
           "offered_because":"finds text blocks, marginalia and seals on manuscript pages",
           "pin":{"hf":"ultralytics/yolov8-layout","revision":"main"},"jobs":["find-regions"],"licence":"agpl-3.0",
           "open_licence":false,"size":"0.09 GB","size_gb":0.09,
           "measured":"unmeasured on your pages until a bake-off measures it","in_recipe_rules":true,
           "installed":false,"runs_where":"this_mac","availability":"download","availability_words":"Download"}],
         "sources":[{"source":"shipped","state":"read","count":1,"detail":"the cards that ship with Fichero"}]}
        """
        return try? JSONDecoder().decode(Components.Schemas.ModelCandidateList.self, from: Data(json.utf8))
    }()
}

#Preview("Review the licence for Find regions") {
    LicenceReviewSheet(
        finder: ModelFinderStore(client: FicheroClient(libraryPath: nil), list: ModelFinderStore.licencePreviewList),
        setup: RecipeSetupStore(client: FicheroClient(libraryPath: nil)),
        step: .init(id: "regions", job: "find-regions"),
        onDone: {},
        loadsCandidates: false
    )
}
