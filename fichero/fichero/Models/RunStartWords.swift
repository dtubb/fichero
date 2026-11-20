import Foundation

/// What a hand run that cannot start says, and the alert's title for it (`runner.hand-run.same-contract`, #6602): a start
/// failure is not an "Import Error". The window's one error line (`importError`) carries these words; `alertTitle(for:)` names
/// the alert from them.
enum RunStartWords {
    static let title = "Couldn't Start the Run"
    static let lostTrackTitle = "Chain Run"
    static let importTitle = "Import Error"

    static let noSelection = "Select one or more documents before running a workflow."
    static let noLibrary = "No project is open, so the workflow cannot run."
    static let notRunnableHere = "This workflow is not in this project's library, so it cannot run here. Reopen the menu and choose it again."
    static let workflowPrefix = "Workflow failed to start: "

    /// A workflow that did not start, with the engine's own words when it gave them.
    static func workflowStartFailure(_ error: Error) -> String {
        workflowPrefix + error.localizedDescription
    }

    static let stopTitle = "Couldn't Stop the Run"
    static let resumeTitle = "Couldn't Continue the Run"

    /// A Stop the engine did not take, with its words: the run may still be going.
    static func stopFailure(_ error: Error) -> String {
        "The run may still be going. " + error.localizedDescription
    }

    /// A Continue the engine did not take, with its words: the run stays paused.
    static func resumeFailure(_ error: Error) -> String {
        "The run stays paused. " + error.localizedDescription
    }

    /// The title of the window's error alert for `message`: a run's start failure says so; everything else is an import's.
    static func alertTitle(for message: String?) -> String {
        guard let message else { return importTitle }
        if message.hasPrefix(ChainRunWords.lostTrackPrefix) { return lostTrackTitle }
        let starts = [noSelection, noLibrary, notRunnableHere, workflowPrefix, ChainRunWords.noProject, ChainRunWords.engineCannot, "Chain failed to start: "]
        return starts.contains(where: { message.hasPrefix($0) }) ? title : importTitle
    }
}
