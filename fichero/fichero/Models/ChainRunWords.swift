import Foundation

/// What the workflow bar says when a chain cannot start (`activity.run.one-way-to-run`): the engine runs every chain, so
/// there is no second way to run one to fall back to; a failure is said in words.
enum ChainRunWords {
    /// No project is open in this window, so there is no chain service to run on.
    static let noProject = "Open a project to run a chain."

    /// The engine answered 404 to the step route: it is older than this app, or the chain was removed.
    static let engineCannot = "The engine can't run this chain. It may be older than this app, or the chain was removed. "
        + "Update Fichero and try again."

    static func startFailure(_ error: Error) -> String {
        if case ChainServiceError.stepExecutionUnavailable = error { return engineCannot }
        return "Chain failed to start: \(error.localizedDescription)"
    }
}
