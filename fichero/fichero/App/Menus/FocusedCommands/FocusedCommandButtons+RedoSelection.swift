import SwiftUI

/// "Run a Step Again on the Selection" (#6744): the saved recipe's step run again as one run on the pages under
/// the selected folders and items (`RecipeFolderScope.redoPages`). Shown when the selection is not the one folder
/// "Run a Step Again on This Folder" already covers.
struct RunStepAgainOnSelectionMenu: View {
    let pages: [String]
    let library: LibraryManager.LibraryReference?
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        if let library, !pages.isEmpty, !library.recipeSetupStore.redoSteps.isEmpty {
            Menu("Run a Step Again on the Selection") {
                ForEach(library.recipeSetupStore.redoSteps, id: \.steps) { step in
                    Button(step.name) { Task { await run(step.steps, library: library) } }
                }
            }
        }
    }

    private func run(_ redo: [String], library: LibraryManager.LibraryReference) async {
        let store = library.recipeSetupStore
        guard await store.start(redo: redo, documents: pages) else {
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
