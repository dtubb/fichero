import Foundation

/// A first launch (ruled 2026-10-10, `source.onboard.first-launch-offers-setup`): first run is
/// not done and the person has set up no project, so every project the app knows of is the
/// always-there one (which has no name). Setup then opens by itself, offering Set Up a New
/// Project… or Start Without a Project. `LibraryWindow` decides it once when it arms its sheets, so the project
/// setup makes does not close setup under the person.
func firstLaunchOffersSetUp(firstRunCompleted: Bool, knownProjectPaths: [String]) -> Bool {
    !firstRunCompleted && knownProjectPaths.allSatisfy { AlwaysThereProject.isPackage(path: $0) }
}

/// First launch's two choices (ruled 2026-10-10, `source.onboard.first-launch-offers-setup`).
enum FirstLaunchChoices {
    /// The welcome's body, under its title (Daniel's words, 2026-10-11): what Fichero is, where it runs, and what a
    /// project is.
    static let welcomeParagraphs = [
        "Fichero is a workbench for historians and archivists. It reads your scans, photographs and PDFs, "
            + "handwriting as well as print, into text you can correct. Then it sorts the pages into documents, "
            + "finds the people, places and dates in them, and makes everything searchable.",
        "Everything runs on this Mac unless you choose otherwise. Your originals are never changed: Fichero "
            + "either keeps its own copy or reads them where they are.",
        "Your work lives in projects. A project holds one body of material, such as an archive's bundle, a run "
            + "of letters or a set of notebooks, with everything Fichero finds in it. You can have as many as you "
            + "like."
    ]

    /// "Next, your project": what setting one up takes, step by step (Daniel's words, 2026-10-11).
    static let handOffIntro = "Setting up a project takes a few minutes:"
    static let handOffSteps = [
        "Name it and choose where it's kept.",
        "Add your material: copy it in, or read it where it is.",
        "Say what it is: its languages and script, when and where it was written, and the hand.",
        "Choose what Fichero does: read the pages, find the documents, the names, the dates. "
            + "Try each step on a few sample pages first."
    ]
    static let handOffClosing = "Nothing runs until you press Start, and you can change any of it later with "
        + "Project › Set Up…."

    static let setUpNewProject = "Set Up a New Project…"

    /// The plainer choice: close setup and work in the always-there project, which has no name
    /// (ruled 2026-10-10), so the choice names none. The window opens on Sources.
    static let startWithoutProject = "Start Without a Project"
}

// The pages themselves are `SetupStep` and `SetupFlow` (Models/SetupFlow.swift, section 7d).
