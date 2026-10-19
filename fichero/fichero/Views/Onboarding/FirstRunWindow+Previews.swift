import FicheroAPIClient
import SwiftUI

// Every setup page at the window's real size (820 × 600), with a project whose stages are the engine's own words
// for Read, Organise and Names (ruled 2026-10-11: the visual pass is done on these, not by launching the app).

#if DEBUG
@MainActor
enum SetupPreviewFixtures {
    /// The inert preview project, its setup holding three stages, Read and Organise chosen.
    static var project: LibraryManager.LibraryReference {
        let library = LibraryPreviewFixtures.library
        seed(library.recipeSetupStore)
        return library
    }

    static var named: NewProjectStore {
        let store = NewProjectStore(libraryManager: LibraryManager.shared)
        store.name = "Escribanía 1023 · Popayán, 1650–1700"
        return store
    }

    static func seed(_ store: RecipeSetupStore) {
        guard store.stages.isEmpty,
              let items = try? JSONDecoder().decode([Components.Schemas.SetupStage].self, from: Data(stagesJSON.utf8))
        else { return }
        store.stages = items
        store.stageChoice = SetupStageChoice(stages: items.map(RecipeSetupStore.choiceStage),
                                             chosen: Set(items.filter(\.on).map(\.id)))
    }

    /// `GET /api/recipes/stages`, trimmed to three stages, as the engine words them.
    static let stagesJSON = """
    [{"id":"read","title":"Read","sentence":"Reads every page, line by line, handwriting as well as print.",
      "example":"“En la ciudad de Popayán a doce días…” read from the page.",
      "jobs":["read-a-line","correct"],"on":true,"jobs_in_recipe":["read-a-line"],
      "questions":[{"key":"reading_level","ask":"How should it be written out?","kind":"one",
        "options":[{"id":"as_written","title":"As written"},{"id":"expanded","title":"Abbreviations expanded"}],
        "read_by_a_step":true}],
      "needs":[],"sampleable":true,"tried_by":"bake-off"},
     {"id":"organise","title":"Organise",
      "sentence":"Finds which pages belong together as one document, and splits a diary or register into its entries.",
      "example":"Three pages of one letter in a bundle, proposed as one document for you to confirm.",
      "jobs":["find-documents-in-a-folder","split-into-entries"],"on":true,"jobs_in_recipe":["find-documents-in-a-folder"],
      "questions":[{"key":"documents_per_folder","ask":"Are several documents in one folder, or one document per folder?",
        "kind":"one","options":[{"id":"several","title":"Several in one folder"},{"id":"one","title":"One document per folder"}],
        "read_by_a_step":false}],
      "needs":[{"stage":"read","why":"Organise needs Read"}],"sampleable":true,"tried_by":"workflow"},
     {"id":"names","title":"Names","sentence":"Finds the people, places and other names in the text.",
      "example":"“Juan de la Cruz” and “Istmina” marked.","jobs":["find-names-tag-words"],"on":false,
      "jobs_in_recipe":[],"questions":[],"needs":[{"stage":"read","why":"Names needs Read"}],
      "sampleable":true,"tried_by":"workflow"}]
    """

    /// One page of setup in the window's environment, at its real size.
    static func page(_ window: FirstRunWindow) -> some View {
        LibraryPreviewFixtures.environment(window)
            .frame(width: FirstRunWindow.windowSize.width, height: FirstRunWindow.windowSize.height)
    }
}

#Preview("01 Welcome") {
    SetupPreviewFixtures.page(FirstRunWindow(mode: .firstRun))
}

#Preview("02 Models & Services") {
    SetupPreviewFixtures.page(FirstRunWindow(mode: .firstRun, initialStep: .whatFicheroRuns))
}

#Preview("03 Hand-off: next, your project") {
    SetupPreviewFixtures.page(FirstRunWindow(mode: .firstRun, initialStep: .handOff, setsUpAProject: true))
}

#Preview("03b Hand-off: Fichero is ready") {
    SetupPreviewFixtures.page(FirstRunWindow(mode: .firstRun, initialStep: .handOff))
}

#Preview("04 Your Project") {
    SetupPreviewFixtures.page(FirstRunWindow(mode: .newProject, initialStep: .project,
                                             newProject: SetupPreviewFixtures.named))
}

#Preview("05 Add Material") {
    SetupPreviewFixtures.page(FirstRunWindow(mode: .setUp, project: SetupPreviewFixtures.project,
                                             initialStep: .addMaterial))
}

#Preview("06 About the Material") {
    SetupPreviewFixtures.page(FirstRunWindow(mode: .setUp, project: SetupPreviewFixtures.project,
                                             initialStep: .aboutMaterial))
}

#Preview("07 Choose the Stages") {
    SetupPreviewFixtures.page(FirstRunWindow(mode: .setUp, project: SetupPreviewFixtures.project, initialStep: .stages))
}

#Preview("08 Stage: Read") {
    SetupPreviewFixtures.page(FirstRunWindow(mode: .setUp, project: SetupPreviewFixtures.project,
                                             initialStep: .stage("read")))
}

#Preview("09 Stage: Organise") {
    SetupPreviewFixtures.page(FirstRunWindow(mode: .setUp, project: SetupPreviewFixtures.project,
                                             initialStep: .stage("organise")))
}

#Preview("10 Ready") {
    SetupPreviewFixtures.page(FirstRunWindow(mode: .setUp, project: SetupPreviewFixtures.project, initialStep: .ready))
}
#endif
