import FicheroAPIClient
import Foundation

/// A failed run as the generic failure alert (`run.fail.alert-on-a-failed-run`, #6354): the engine's words and fix, and a button for
/// each of its actions, in its order. Nothing is worked out here but which title goes with which action; the words, the fix and the
/// order are the engine's (`RunFailure`, `llm/failure.py`). A cap or images refusal is not an alert of this kind: the cap alert
/// (`CloudRefusalAlert`) answers it, so its actions get no button here.
enum RunFailurePrompt {
    /// The button for an action, or nil for one this alert does not offer.
    nonisolated static func title(for kind: Components.Schemas.FailureAction.KindPayload) -> String? {
        switch kind {
        case .retry: "Run It Again"
        case .resume: "Resume"
        case .openSettings: "Open Settings…"
        case .chooseModel: "Choose a Model…"
        case .reportBug: "Send a Bug Report…"
        case .reconnect: "Reconnect…"
        case .raiseTo, .allowEverywhere, .allowProject, .allowOnce, .overCapOnce: nil
        }
    }

    /// The alert for `failure`. `workflow` names the run in the title ("<Workflow> stopped"); `perform` does an action; `showInActivity`,
    /// when given, adds the "Show in Activity" button after the actions.
    static func make(
        _ failure: Components.Schemas.RunFailure,
        workflow: String? = nil,
        perform: @escaping (Components.Schemas.FailureAction) -> Void,
        showInActivity: (() -> Void)? = nil
    ) -> FailureAlertPrompt {
        var buttons: [(label: String, action: () -> Void)] = (failure.actions ?? []).compactMap { action in
            guard let label = title(for: action.kind) else { return nil }
            return (label, { perform(action) })
        }
        if let showInActivity { buttons.append(("Show in Activity", showInActivity)) }
        return FailureAlertPrompt(
            title: workflow.map { "\($0) stopped" } ?? "Fichero stopped this run",
            message: FailureAlertPrompt.message(why: failure.words, fix: failure.fix),
            fixes: buttons.enumerated().map { FailureAlertPrompt.Fix(id: $0.offset, label: $0.element.label, action: $0.element.action) })
    }
}
