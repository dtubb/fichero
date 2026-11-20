import Foundation
#if canImport(AppKit)
import AppKit
#endif

/// The refusal a menu's Start or "Run the Recipe on This Folder…" shows where the person pressed (`runner.hand-run.same-contract`,
/// #6602): those verbs have no window state to carry an error line, so the engine's words come up as an alert.
enum RunRefusalAlert {
    static let title = "Couldn't Start the Run"
    static let fallback = "Nothing was started. Set Up… shows the steps and why."

    /// The words to show: the engine's error from the start call, else the plan's first refusal, else the fallback.
    static func words(startError: String?, planRefusals: [String]) -> String {
        if let startError, !startError.isEmpty { return startError }
        if let first = planRefusals.first, !first.isEmpty { return first }
        return fallback
    }

    @MainActor
    static func show(_ words: String) {
        #if canImport(AppKit)
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = title
        alert.informativeText = words
        alert.addButton(withTitle: "OK")
        alert.runModal()
        #endif
    }
}
