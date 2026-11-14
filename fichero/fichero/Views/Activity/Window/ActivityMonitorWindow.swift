import SwiftUI

/// The ONE Activity window (`activity.window.is-the-pane-plus-inspector`, `activity.one-window`, #6441): an Activity pane
/// over every open project and the Inspector beside it showing the selected row (`ActivityInspectorSection`). No view tree
/// of its own and no detail window: Show in Activity writes `ActivityWindowSelectionState.reveal`, then opens this window.
struct ActivityMonitorWindow: View {
    @State private var selectionState = ActivityWindowSelectionState.shared
    @State private var showsInspector = true

    var body: some View {
        ActivityPaneView(libraryId: nil, paneKey: "activity.window", reveal: selectionState.reveal,
                         onSelect: { selectionState.pick = $0 })
            .inspector(isPresented: $showsInspector) {
                ActivityInspectorSection(pick: selectionState.pick)
                    .inspectorColumnWidth(min: 280, ideal: 380, max: 640)
            }
            .toolbar {
                Button { showsInspector.toggle() } label: { Label("Inspector", systemImage: "sidebar.trailing") }
                    .help(showsInspector ? "Hide the Inspector" : "Show the Inspector")
            }
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
