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
    /// The welcome at the top of first launch's setup: what Fichero does, and that the first step
    /// is a project.
    static let welcome = "Fichero reads, organises and connects your scanned sources, PDFs and notes. "
        + "The first step is setting up a project for your material."
    static let setUpNewProject = "Set Up a New Project…"

    /// The plainer choice: close setup and work in the always-there project, which has no name
    /// (ruled 2026-10-10), so the choice names none. The window opens on Sources.
    static let startWithoutProject = "Start Without a Project"
}

// The pages themselves are `SetupStep` and `SetupFlow` (Models/SetupFlow.swift, section 7d).
