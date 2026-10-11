import FicheroAPIClient
import SwiftUI

/// Set Up… › Ready's model finder for one step (#5611, #5619): the finder for the step's job, the
/// project's scripts and languages and its first material, with Use for This Step where the plan
/// offers an installed reader instead of the step's download.
struct ModelFinderSheet: View {
    let project: LibraryManager.LibraryReference
    let setup: RecipeSetupStore
    let step: RecipeStepsView.FinderStep
    let onDone: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(Self.title(job: step.job, step: setup.title(ofStepId: step.id), setup: setup)).font(.headline)
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    ModelFinderView(
                        store: project.modelFinderStore,
                        query: setup.finderQuery(job: step.job, step: step.id),
                        activity: project.activityStore,
                        step: .init(id: step.id, setup: setup)
                    )
                    // Try them on your pages (#5660 item 7): the same comparison the step offers in Ready.
                    if let context = BakeoffSection.Context(project: project).forStep(step.job) {
                        Divider()
                        Text("Try them on your pages").font(.headline)
                        BakeoffSection(context: context, setup: setup)
                    }
                }
            }
            HStack {
                Spacer()
                Button("Done", action: onDone).keyboardShortcut(.defaultAction)
            }
        }
        .padding()
        .frame(minWidth: 480, minHeight: 420)
    }

    /// "Find a Reader for Read each line" for a step that reads the material, else "Choose a Model for Find
    /// statements" (#5619: the finder answers for any step's job).
    static func title(job: String, step: String, setup: RecipeSetupStore) -> String {
        setup.readsMaterial(job) ? "Find a Reader for \(step)" : "Choose a Model for \(step)"
    }
}

#Preview("Find a Reader for Read each line") {
    LibraryPreviewFixtures.environment(
        ModelFinderSheet(
            project: LibraryPreviewFixtures.library,
            setup: RecipeSetupStore(client: FicheroClient(libraryPath: nil)),
            step: .init(id: "read-a-line", job: "read-a-line"),
            onDone: {}
        )
    )
}
