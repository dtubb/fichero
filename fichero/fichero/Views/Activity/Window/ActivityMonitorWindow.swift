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
                         revealFiles: selectionState.revealFiles, onSelect: { selectionState.pick = $0 },
                         onRevealed: { selectionState.reveal = nil; selectionState.revealFiles = nil })
            .inspector(isPresented: $showsInspector) {
                ActivityInspectorSection(pick: selectionState.pick)
                    .inspectorColumnWidth(min: 280, ideal: 380, max: 640)
            }
            .toolbar {
                Button { showsInspector.toggle() } label: { Label("Inspector", systemImage: "sidebar.trailing") }
                    .help(showsInspector ? "Hide the Inspector" : "Show the Inspector")
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
