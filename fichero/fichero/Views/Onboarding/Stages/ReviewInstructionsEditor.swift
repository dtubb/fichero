import FicheroAPIClient
import SwiftUI

/// The review stage's per-pass instructions (`source.job.review-instructions-are-editable`, #6128): reads the engine's
/// passes for this project and shows them in the editor below.
struct ReviewInstructionsSection: View {
    let store: RecipeSetupStore
    @State private var instructions: ReviewInstructionsStore

    init(store: RecipeSetupStore) {
        self.store = store
        _instructions = State(initialValue: ReviewInstructionsStore(client: store.client))
    }

    var body: some View {
        @Bindable var store = store
        ReviewInstructionsEditor(passes: instructions.passes, errorMessage: instructions.errorMessage,
                                 answers: $store.jobAnswers)
            .task { await instructions.load() }
    }
}

/// Each pass shows the engine's default as it is sent, built from the project's language, script and date, and the
/// person may change it. Reset to default sends a blank, which the engine reads as no edit.
struct ReviewInstructionsEditor: View {
    let passes: [Components.Schemas.ReviewInstruction]
    let errorMessage: String?
    @Binding var answers: RecipeSetupAnswers.JobAnswers

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Instructions for each pass")
                .font(.headline)
            Text("Changes apply to pages reviewed from now on; pages already reviewed are not reviewed again. "
                 + "The defaults follow your saved answers: save to see them change.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(passes, id: \.lens) { pass in
                DisclosureGroup(pass.lens.replacingOccurrences(of: "-", with: " ").capitalized) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(pass.profile)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                        TextEditor(text: Binding(
                            get: { answers.reviewText(for: pass.lens, default: pass._default) },
                            set: { answers.setReview($0, for: pass.lens, default: pass._default) }
                        ))
                        .font(.body)
                        .frame(minHeight: 140)
                        .accessibilityIdentifier("setup.review.instructions.\(pass.lens)")
                        Button("Reset to default") { answers.setReview("", for: pass.lens, default: pass._default) }
                            .disabled(answers.reviewInstructions[pass.lens] == nil)
                    }
                }
            }
            if let errorMessage {
                Text(errorMessage).font(.caption).foregroundStyle(.red)
            }
        }
    }
}

#Preview("Three passes, orthography edited") {
    @Previewable @State var answers: RecipeSetupAnswers.JobAnswers = {
        var answers = RecipeSetupAnswers.JobAnswers()
        answers.reviewInstructions = ["orthography": "Only normalise u and v."]
        return answers
    }()
    ReviewInstructionsEditor(
        passes: ["abbreviations", "orthography", "names-and-dates"].map {
            Components.Schemas.ReviewInstruction(
                lens: $0, _default: "Check the \($0) of this page against the image.",
                text: "Check the \($0) of this page against the image.", edited: false,
                profile: "Built from the Spanish colonial profile.")
        },
        errorMessage: nil, answers: $answers
    )
    .padding()
    .frame(width: 460)
}
