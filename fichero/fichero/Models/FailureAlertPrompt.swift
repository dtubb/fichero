import Foundation

/// An alert that says what happened and what to do about it: a title, one message (the why and the fix) and the buttons that
/// act on it (`run.fail.alert-on-a-failed-run`, #6354). Nothing here names a run, a pairing or a sharing step: a wrapper turns what
/// failed into this (`RunFailurePrompt`), and `FailureAlert` shows it.
struct FailureAlertPrompt: Identifiable {
    /// One button that acts on the failure: its label and what it does. The alert dismisses itself after it.
    struct Fix: Identifiable {
        let id: Int
        let label: String
        let action: () -> Void
    }

    let id = UUID()
    let title: String
    /// What happened and what to do, as the one message the alert shows.
    let message: String
    /// The buttons that act, in the order to offer them; empty for an alert that only says.
    let fixes: [Fix]
    /// The button that closes the alert without acting.
    let dismissLabel: String

    init(title: String, message: String, fixes: [Fix] = [], dismissLabel: String = "Not Now") {
        self.title = title
        self.message = message
        self.fixes = fixes
        self.dismissLabel = dismissLabel
    }

    /// The message from what happened and what to do: each on its own paragraph, an empty one left out.
    static func message(why: String, fix: String?) -> String {
        [why, fix ?? ""].filter { !$0.isEmpty }.joined(separator: "\n\n")
    }
}
