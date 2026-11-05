import FicheroAPIClient
import Foundation

/// A hand run the engine refused for a cloud rule, and the buttons that answer it (`ai.cloud.alert-on-hand-run-
/// paths`, #6349).
/// The words, the figures and the fixes are the engine's (`detail.refusal`); nothing is worked out here but
/// which button runs
/// which action.
struct CloudRefusalPrompt: Identifiable {
    /// What a once button sends with the same run again; nothing is written to a setting.
    struct Once: Equatable {
        var allowCloud = false
        var overCap = false
    }

    /// What a button does.
    enum Action: Equatable {
        case allowEverywhere   // the app's places answer, the audited action
        case allowProject      // `POST /api/recipes/project/allow-cloud`
        case runAgain(Once)    // this run only
        case openSettings
        /// The cap the refusal names, raised to `usd` (the audited action for its scope), then the run goes again.
        case raiseCap(Components.Schemas.CloudRefusal.KindPayload, Components.Schemas.CloudRefusal.ScopePayload, usd: Double)
    }

    struct Choice: Identifiable, Equatable {
        let id: Int
        let title: String
        let action: Action
    }

    let id = UUID()
    let refusal: Components.Schemas.CloudRefusal
    /// Runs the refused run again with the once overrides; set by the run that was refused.
    let resend: (Once) -> Void

    /// The buttons in the engine's order. A raise-to fix raises the cap it names to the engine's
    /// figure (no figure: the caps in Settings); the figure is shown in its words.
    var choices: [Choice] {
        let fixes = refusal.fixes ?? []
        return fixes.enumerated().map { index, fix in
            switch fix.kind {
            case .allowEverywhere: Choice(id: index, title: "Allow for all projects", action: .allowEverywhere)
            case .allowProject: Choice(id: index, title: "Allow for this project", action: .allowProject)
            case .allowOnce: Choice(id: index, title: "Allow this once", action: .runAgain(Once(allowCloud: true)))
            case .overCapOnce:
                Choice(id: index, title: "Run past the cap this once", action: .runAgain(Once(overCap: true)))
            case .raiseTo:
                if let usd = fix.usd {
                    Choice(id: index, title: "Raise the cap to \(usd.formatted(.currency(code: "USD")))",
                           action: .raiseCap(refusal.kind, refusal.scope, usd: usd))
                } else {
                    Choice(id: index, title: "Raise the cap…", action: .openSettings)
                }
            case .openSettings: Choice(id: index, title: "Open Settings…", action: .openSettings)
            }
        }
    }
}
