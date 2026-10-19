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
    /// The welcome's body (the owner's words, 2026-10-19, #5828).
    static let welcomeParagraphs = [
        "Fichero is a Mac app to read and work with archives. It finds the lines on a page and transcribes "
            + "handwritten and typed documents in many languages into text you can correct. It reads scans, "
            + "photographs, PDFs and other image files, and pages from IIIF servers.",
        "It helps you find the people, places and dates in your documents, and makes them searchable. You can "
            + "navigate, search and edit the results.",
        "Fichero is a workbench. Each page keeps its image, the lines found on it and every reading of them, so you "
            + "can compare readings, correct a line against the picture, and see where each result came from. Your "
            + "originals are never changed."
    ]

    /// Your First Project (the owner's words, 2026-10-19).
    static let handOffParagraphs = [
        "Your work lives in projects. A project holds one body of material, such as an archive's bundle of files or "
            + "a set of notebooks. You can have as many as you like.",
        "Setting up a project takes a few minutes. You add your files, describe them (language, script, period) and "
            + "say what you want from them. Fichero suggests the best models for each step and shows you the plan "
            + "before any work starts."
    ]

    static let setUpNewProject = "Set Up a New Project..."
    static let startWithoutProject = "Start Without a Project"

}

// The pages themselves are `SetupStep` and `SetupFlow` (Models/SetupFlow.swift, section 7d).
