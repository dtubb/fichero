import Foundation

/// What the workflow bar says when a chain cannot start (`activity.run.one-way-to-run`): the engine runs every chain, so
/// there is no second way to run one to fall back to; a failure is said in words.
enum ChainRunWords {
    /// No project is open in this window, so there is no chain service to run on.
    static let noProject = "Open a project to run a chain."

    /// The engine answered 404 to the step route: it is older than this app, or the chain was removed.
    static let engineCannot = "The engine can't run this chain. It may be older than this app, or the chain was removed. "
        + "Update Fichero and try again."

    /// The engine stopped answering the chain's status polls (#6602): the chain may still be running there.
    static func lostTrack(afterFailedPolls count: Int) -> String {
        "Lost track of the chain: the engine did not answer \(count) status checks in a row. "
            + "It may still be running; Activity shows where it is."
    }

    /// The chain was still running when the app stopped watching it.
    static let stoppedWatching = "Lost track of the chain: it was still running after 4 hours, so the app stopped watching. "
        + "It may still be running; Activity shows where it is."

    /// What both messages above start with, so the alert can be titled for them.
    static let lostTrackPrefix = "Lost track of the chain: "

    static func startFailure(_ error: Error) -> String {
        if case ChainServiceError.stepExecutionUnavailable = error { return engineCannot }
        return "Chain failed to start: \(error.localizedDescription)"
    }
}
