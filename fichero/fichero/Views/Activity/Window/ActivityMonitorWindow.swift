import SwiftUI

/// The ONE Activity window (`activity.window.is-the-pane-plus-inspector`, `activity.one-window`, #6441): an Activity pane
/// over every open project and the Inspector beside it showing the selected row (`ActivityInspectorSection`). No view tree
/// of its own and no detail window: Show in Activity writes `ActivityWindowSelectionState.reveal`, then opens this window.
struct ActivityMonitorWindow: View {
    @State private var selectionState = ActivityWindowSelectionState.shared
    @State private var showsInspector = true
    /// The window's own step stack: Delete, Archive and Put Back here are undone by Edit › Undo in this window.
    @State private var steps = WindowSteps()

    var body: some View {
        ActivityPaneView(libraryId: nil, paneKey: "activity.window", reveal: selectionState.reveal,
                         revealFiles: selectionState.revealFiles, revealAll: selectionState.revealAll,
                         onSelect: { selectionState.pick = $0 },
                         onRevealed: {
                             selectionState.reveal = nil; selectionState.revealFiles = nil; selectionState.revealAll = nil
                         })
            .inspector(isPresented: $showsInspector) {
                ActivityInspectorSection(pick: selectionState.pick)
                    .inspectorColumnWidth(min: 280, ideal: 380, max: 640)
            }
            .toolbar {
<<<<<<< HEAD
                // Activity Monitor's toolbar (decision 22): the verbs at the leading edge, the Inspector toggle at the end.
                ToolbarItem(placement: .navigation) { ActivityToolbarVerbsBar() }
=======
                // Xcode's run controls at the far left (decision 30): Play/Pause and Stop for all work; the Inspector toggle at the end.
                ToolbarItem(placement: .navigation) { ActivityRunControlsButtons() }
>>>>>>> 8599ab5c0a (feat(activity): Xcode's run controls at the far left of the Activity window and every main window: one Play/Pause that turns, and Stop, for all work in every open project (#6588))
                ToolbarItem(placement: .primaryAction) {
                    Button { showsInspector.toggle() } label: { Label("Inspector", systemImage: "sidebar.trailing") }
                        .help(showsInspector ? "Hide the Inspector" : "Show the Inspector")
                }
            }
            .environment(steps)
            .focusedSceneValue(\.windowSteps, steps)
            .overlay(alignment: .bottom) { UndoRefusalNotice(steps: steps) }
            .navigationTitle("Activity")
            .frame(minWidth: 720, minHeight: 520)
            .accessibilityIdentifier("activity.window")
    }
}

#Preview("The Activity window") {
    ActivityMonitorWindow()
        .environment(LibraryManager.shared)
        .frame(width: 900, height: 520)
}
