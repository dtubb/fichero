import SwiftUI

/// Settings › AI's model finder (#5611, `source.find.app-finder-three-hosts`): readers for the open
/// project's scripts and languages, from its saved setup answers (read into a store of its own, as the
/// project Inspector does, so a setup in progress elsewhere keeps its draft). With no project open it
/// says to open one: the scripts and languages are a project's answers.
struct SettingsModelFinderSection: View {
    @Environment(LibraryManager.self) private var libraryManager

    @State private var setup: RecipeSetupStore?

    private var library: LibraryManager.LibraryReference? {
        libraryManager.currentLibraryId.flatMap { libraryManager.getLibrary(id: $0) }
    }

    var body: some View {
        Section("Find a Reader") {
            if let library {
                if let setup {
                    ProjectModelFinder(library: library, setup: setup)
                } else {
                    ProgressView().controlSize(.small)
                }
            } else {
                Text("Open a project to find readers for its scripts and languages.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
        }
        .task(id: library?.id) {
            setup = nil
            guard let library else { return }
            let store = RecipeSetupStore(client: library.ficheroClient, topics: library.topicStore)
            await store.loadSaved()
            guard !Task.isCancelled else { return }
            setup = store
        }
    }
}

#Preview("Find a Reader in Settings") {
    Form { SettingsModelFinderSection() }
        .formStyle(.grouped)
        .environment(LibraryManager.shared)
        .frame(width: 480, height: 240)
}
