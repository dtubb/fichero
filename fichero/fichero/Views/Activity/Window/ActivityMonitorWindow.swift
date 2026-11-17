import SwiftUI

/// The ONE Activity window (`activity.window.is-the-pane-plus-inspector`, `activity.one-window`, #6441): an Activity pane
/// over every open project and the Inspector beside it showing the selected row (`ActivityInspectorSection`). No view tree
/// of its own and no detail window: Show in Activity writes `ActivityWindowSelectionState.reveal`, then opens this window.
struct ActivityMonitorWindow: View {
    @State private var selectionState = ActivityWindowSelectionState.shared
    /// The window's own step stack: Delete, Archive and Put Back here are undone by Edit › Undo in this window.
    @State private var steps = WindowSteps()

    var body: some View {
        ActivityPaneView(libraryId: nil, paneKey: "activity.window", reveal: selectionState.reveal,
                         revealFiles: selectionState.revealFiles, revealAll: selectionState.revealAll,
                         onSelect: { selectionState.pick = $0 },
                         onRevealed: {
                             selectionState.reveal = nil; selectionState.revealFiles = nil; selectionState.revealAll = nil
                         },
                         windowInspector: { AnyView(ActivityInspectorSection(pick: selectionState.pick)) })
            .environment(steps)
            .focusedSceneValue(\.windowSteps, steps)
            .overlay(alignment: .bottom) { UndoRefusalNotice(steps: steps) }
            .navigationTitle("Activity")
            // The columns' sizes fit in this minimum (`ActivityPaneView+WindowLayout.swift`, #6661).
            .frame(minWidth: ActivityPaneView.windowMinWidth, minHeight: ActivityPaneView.windowMinHeight)
            .accessibilityIdentifier("activity.window")
    }
}

#Preview("The Activity window") {
    ActivityMonitorWindow()
        .environment(LibraryManager.shared)
        .frame(width: 1200, height: 640)
}
