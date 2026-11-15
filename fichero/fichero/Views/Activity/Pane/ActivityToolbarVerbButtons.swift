import SwiftUI

/// Pause, Continue and Stop as toolbar buttons (`activity.window.toolbar-verbs`, decision 24, #6588): in the Activity window,
/// and in a main window's toolbar beside the sidebar while its Activity pane holds the focus. They act on the focused pane's
/// selection by the Mail rule, through the one verb list (`ActivityPaneVerb`) the pane publishes as `activityVerbs`, the same
/// target Project › Activity reads: never a second path.
struct ActivityToolbarVerbButtons: View {
    @FocusedValue(\.activityVerbs) private var target
    /// A main window's toolbar draws nothing while no Activity pane holds the focus; the Activity window always draws them.
    var hidesWithoutAPane = false

    /// The three, in the toolbar's order.
    static let verbs: [ActivityPaneVerb] = [.pause, .resume, .stop]

    /// The toolbar's verbs the target's selection enables.
    static func enabled(_ target: ActivityVerbTarget?) -> [ActivityPaneVerb] {
        verbs.filter { target?.enabled.contains($0) ?? false }
    }

    var body: some View {
        if target != nil || !hidesWithoutAPane {
            ControlGroup {
                ForEach(Self.verbs) { verb in
                    Button { target?.perform(verb) } label: { Label(verb.title, systemImage: verb.symbol) }
                        .help("\(verb.title) the selected rows")
                        .disabled(!Self.enabled(target).contains(verb))
                }
            }
            .accessibilityIdentifier("activity.toolbar.verbs")
        }
    }
}

#Preview("Toolbar verbs") {
    ActivityToolbarVerbButtons()
        .padding()
}
