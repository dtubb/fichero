import SwiftUI

/// Run Step ▸ on the selected regions, lines or words (`segment-actions.run-step-on-selection`, #6069): the recipe's steps,
/// each named with what it will run on ("Run Read on 2 segments"), sent as one `POST /api/recipes/project/start` with
/// `steps` and `segments`. One component for every right-click menu on segments.
struct RunStepOnSegmentsMenu: View {
    let ids: [String]
    /// The menu's name; "Read Again" under a line whose words may be out of date (`SegmentReread.againTitle`).
    var label = RunStepOnSegmentsMenu.title
    @Environment(LibraryManager.self) private var libraryManager: LibraryManager?
    @Environment(DocumentStore.self) private var documentStore: DocumentStore?
    @Environment(\.openWindow) private var openWindow

    /// The one name on every surface (`RunStepAgainOnSelectionMenu.title`).
    nonisolated static let title = "Run Step"

    /// "Run Read on 2 segments", "Run Read on 1 segment": the step by its own name and the count of what is selected.
    nonisolated static func itemTitle(step: String, count: Int) -> String {
        "Run \(step) on \(count) \(count == 1 ? "segment" : "segments")"
    }

    /// Whether the menu is shown: something is selected and the recipe has steps to run.
    nonisolated static func isOffered(ids: [String], stepCount: Int) -> Bool { !ids.isEmpty && stepCount > 0 }

    private var library: LibraryManager.LibraryReference? {
        documentStore.flatMap { libraryManager?.library(owningService: $0) }
    }

    var body: some View {
        if let library, Self.isOffered(ids: ids, stepCount: library.recipeSetupStore.redoSteps.count) {
            Menu(label) {
                ForEach(library.recipeSetupStore.redoSteps, id: \.steps) { step in
                    Button(Self.itemTitle(step: step.name, count: ids.count)) {
                        Task { await run(step.steps, library: library) }
                    }
                }
            }
        }
    }

    private func run(_ steps: [String], library: LibraryManager.LibraryReference) async {
        let store = library.recipeSetupStore
        guard await store.start(steps: steps, segments: ids) else {
            RunRefusalAlert.show(RunRefusalAlert.words(startError: store.errorMessage, planRefusals: []))
            return
        }
        #if os(macOS)
        if let selection = FirstRunWindow.startedRunSelection(jobId: store.startedRunJobId, projectId: library.id) {
            ActivityWindowSelectionState.shared.select(selection)
            openWindow(id: ActivityWindowSelectionState.monitorWindowID)
        }
        #endif
    }
}
